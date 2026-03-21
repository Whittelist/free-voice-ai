from __future__ import annotations

import contextlib
import hashlib
import io
import json
import math
import os
import platform
import re
import secrets
import struct
import tempfile
import threading
import time
import traceback
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import requests
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from starlette.middleware.base import BaseHTTPMiddleware

try:
    from local_engine_windows import __version__
except ModuleNotFoundError:  # pragma: no cover - supports direct script execution
    from __init__ import __version__

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = int(os.getenv("LOCAL_ENGINE_PORT", "57641"))
DEFAULT_SERVICE_NAME = "studio-voice-local-engine"
DEFAULT_DATA_DIR = Path(os.getenv("LOCAL_ENGINE_DATA_DIR", Path.home() / ".studio_voice_local"))
DEFAULT_ALLOWED_ORIGINS = os.getenv(
    "LOCAL_ENGINE_ALLOWED_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,https://your-railway-domain.railway.app",
)
DEFAULT_ALLOWED_ORIGIN_REGEX = os.getenv(
    "LOCAL_ENGINE_ALLOWED_ORIGIN_REGEX",
    r"^https://[a-z0-9.-]+(:\d+)?$|^http://localhost(:\d+)?$|^http://127\.0\.0\.1(:\d+)?$",
)
SIMULATE_DOWNLOAD = os.getenv("SIMULATE_MODEL_DOWNLOAD", "0") != "0"
INFERENCE_BACKEND = os.getenv("LOCAL_ENGINE_INFERENCE_BACKEND", "auto").strip().lower()
RELEASE_MODEL_ON_UNLOAD = os.getenv("LOCAL_ENGINE_RELEASE_MODEL_ON_UNLOAD", "1") != "0"
REQUIRE_GPU = os.getenv("LOCAL_ENGINE_REQUIRE_GPU", "0") == "1"
DOWNLOAD_CHUNK_BYTES = 1024 * 512
DOWNLOAD_SLEEP_SECONDS = 0.015
PUBLIC_PATHS = {"/health", "/version", "/docs", "/openapi.json", "/redoc"}
PRO_PROFILE = "pro_multilingual_balanced"

MODEL_PROFILES: dict[str, dict[str, Any]] = {
    PRO_PROFILE: {
        "display_name": "Chatterbox multilingual balanced (ES/EN)",
        "languages": ["es", "en"],
        "source_model": "onnx-community/chatterbox-multilingual-ONNX",
        "components": [
            {
                "name": "conditional_decoder.onnx_data",
                "size_bytes": 534_000_000,
                "simulated_size_bytes": 48_000_000,
                "url": "https://huggingface.co/onnx-community/chatterbox-multilingual-ONNX/resolve/main/onnx/conditional_decoder.onnx_data",
            },
            {
                "name": "speech_encoder.onnx_data",
                "size_bytes": 591_000_000,
                "simulated_size_bytes": 64_000_000,
                "url": "https://huggingface.co/onnx-community/chatterbox-multilingual-ONNX/resolve/main/onnx/speech_encoder.onnx_data",
            },
            {
                "name": "embed_tokens.onnx_data",
                "size_bytes": 68_400_000,
                "simulated_size_bytes": 24_000_000,
                "url": "https://huggingface.co/onnx-community/chatterbox-multilingual-ONNX/resolve/main/onnx/embed_tokens.onnx_data",
            },
            {
                "name": "language_model_q4f16.onnx_data",
                "size_bytes": 305_000_000,
                "simulated_size_bytes": 92_000_000,
                "url": "https://huggingface.co/onnx-community/chatterbox-multilingual-ONNX/resolve/main/onnx/language_model_q4f16.onnx_data",
            },
            {
                "name": "runtime_metadata.bin",
                "size_bytes": 8_000_000,
                "simulated_size_bytes": 8_000_000,
                "url": "",
            },
        ],
    }
}


@dataclass
class DownloadJob:
    profile: str
    status: str = "idle"
    stage: str = "idle"
    progress: float = 0.0
    downloaded_bytes: int = 0
    total_bytes: int = 0
    error: str | None = None
    started_at: float = 0.0
    updated_at: float = 0.0

    def to_payload(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "status": self.status,
            "stage": self.stage,
            "progress": round(self.progress, 2),
            "downloaded_bytes": self.downloaded_bytes,
            "total_bytes": self.total_bytes,
            "error": self.error,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
        }


class EngineHTTPError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


class DownloadRequest(BaseModel):
    profile: str = Field(default=PRO_PROFILE)


class LoadRequest(BaseModel):
    profile: str = Field(default=PRO_PROFILE)


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=3000)
    language: str = Field(default="es")
    quality_profile: str = Field(default=PRO_PROFILE)


class EngineRuntime:
    def __init__(self, logger: Callable[[str], None] | None = None) -> None:
        self.log = logger if logger is not None else lambda msg: None
        self.data_dir = DEFAULT_DATA_DIR
        self.cache_dir = self.data_dir / "cache"
        self.state_path = self.data_dir / "state.json"
        self.token_path = self.data_dir / "api_token.txt"
        self.allowed_origins = [origin.strip() for origin in DEFAULT_ALLOWED_ORIGINS.split(",") if origin.strip()]
        self.allowed_origin_regex = DEFAULT_ALLOWED_ORIGIN_REGEX.strip() or None
        self.allowed_origin_pattern = re.compile(self.allowed_origin_regex) if self.allowed_origin_regex else None
        self.simulate_download = SIMULATE_DOWNLOAD

        self._lock = threading.Lock()
        self.download_jobs: dict[str, DownloadJob] = {}
        self.download_threads: dict[str, threading.Thread] = {}
        self.loading_profiles: set[str] = set()
        self.loaded_profile: str | None = None
        self.backend_lock = threading.Lock()

        # Real-inference backend state (Chatterbox runtime).
        self.inference_backend = "mock"
        self.backend_mode = INFERENCE_BACKEND
        self.real_backend_available = False
        self.real_backend_error: str | None = None
        self.real_backend_device = "cpu"
        self.real_backend_cache_ready = False
        self._torch: Any | None = None
        self._np: Any | None = None
        self._chatterbox_class: Any | None = None
        self._real_model: Any | None = None

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.api_token = self._load_or_create_token()
        self._init_inference_backend()
        self._load_state()

    def _load_or_create_token(self) -> str:
        if self.token_path.exists():
            token = self.token_path.read_text(encoding="utf-8").strip()
            if token:
                return token
        token = secrets.token_urlsafe(32)
        self.token_path.write_text(token, encoding="utf-8")
        self.log("Token local generado por primera vez.")
        return token

    def _save_state(self) -> None:
        payload = {"loaded_profile": self.loaded_profile}
        self.state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _load_state(self) -> None:
        if not self.state_path.exists():
            return
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            loaded_profile = payload.get("loaded_profile")
            if isinstance(loaded_profile, str):
                self.loaded_profile = loaded_profile
        except json.JSONDecodeError:
            self.log("No se pudo leer state.json, se ignora.")

    def _init_inference_backend(self) -> None:
        mode = self.backend_mode
        if mode not in {"auto", "mock", "chatterbox"}:
            self.log(f"LOCAL_ENGINE_INFERENCE_BACKEND invalido ({mode}), usando auto.")
            mode = "auto"
            self.backend_mode = "auto"

        if mode == "mock":
            self.inference_backend = "mock"
            self.log("Backend de inferencia: mock (audio sintetico).")
            return

        try:
            import numpy as np
            import perth
            import torch
            from chatterbox.mtl_tts import ChatterboxMultilingualTTS

            # Some perth builds silently disable PerthImplicitWatermarker when an optional
            # import (commonly pkg_resources) is missing. In that case chatterbox crashes
            # at model init with "'NoneType' object is not callable". Fallback to dummy
            # watermarker to keep local inference usable.
            if getattr(perth, "PerthImplicitWatermarker", None) is None:
                dummy_watermarker = getattr(perth, "DummyWatermarker", None)
                if dummy_watermarker is not None:
                    perth.PerthImplicitWatermarker = dummy_watermarker
                    self.log(
                        "WARN: PerthImplicitWatermarker no disponible; se usara DummyWatermarker "
                        "(sin watermark implicito)."
                    )
                else:
                    self.log("WARN: Perth watermarker no disponible; la carga del backend puede fallar.")

            self._torch = torch
            self._np = np
            self._chatterbox_class = ChatterboxMultilingualTTS
            self.real_backend_available = True

            if torch.cuda.is_available():
                self.real_backend_device = "cuda"
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                self.real_backend_device = "mps"
            else:
                self.real_backend_device = "cpu"

            self.inference_backend = "chatterbox"
            self.log(f"Backend de inferencia: chatterbox ({self.real_backend_device}).")
        except Exception as error:  # noqa: BLE001
            self.real_backend_available = False
            self.real_backend_error = str(error)
            self.inference_backend = "mock"
            if mode == "chatterbox":
                self.log(f"No se pudo iniciar backend chatterbox: {error}")
            self.log("Fallback al backend mock.")

    def _ensure_real_backend_model(self) -> None:
        if self.inference_backend != "chatterbox":
            raise EngineHTTPError(503, "REAL_BACKEND_UNAVAILABLE", "Backend real no disponible.")
        if not self.real_backend_available:
            detail = self.real_backend_error or "Dependencias no instaladas."
            raise EngineHTTPError(503, "REAL_BACKEND_UNAVAILABLE", detail)
        if REQUIRE_GPU and self.real_backend_device == "cpu":
            raise EngineHTTPError(
                409,
                "GPU_UNAVAILABLE",
                "Este perfil requiere GPU y no se detecto aceleracion compatible.",
            )

        with self.backend_lock:
            if self._real_model is not None:
                return
            try:
                self.log(
                    "Inicializando Chatterbox Multilingual (primera vez puede tardar varios minutos "
                    "por descarga/cache de checkpoints)..."
                )
                assert self._chatterbox_class is not None
                # Workaround for checkpoints serialized with CUDA storages on CPU-only hosts.
                # Some chatterbox versions call torch.load() internally without map_location.
                torch_mod = self._torch
                if torch_mod is None:
                    raise EngineHTTPError(500, "REAL_BACKEND_INIT_FAILED", "torch no disponible.")

                target_device = torch_mod.device(self.real_backend_device)
                original_torch_load = torch_mod.load

                def _safe_torch_load(*args: Any, **kwargs: Any) -> Any:
                    if target_device.type == "cpu" and "map_location" not in kwargs:
                        kwargs["map_location"] = target_device
                    return original_torch_load(*args, **kwargs)

                torch_mod.load = _safe_torch_load
                try:
                    self._real_model = self._chatterbox_class.from_pretrained(device=target_device)
                finally:
                    torch_mod.load = original_torch_load

                self.real_backend_cache_ready = True
                self.log("Chatterbox listo para inferencia local.")
            except EngineHTTPError:
                raise
            except Exception as error:  # noqa: BLE001
                self.real_backend_error = str(error)
                raise EngineHTTPError(500, "REAL_BACKEND_INIT_FAILED", str(error)) from error

    def _release_real_backend_model(self) -> None:
        with self.backend_lock:
            self._real_model = None
            if self._torch is not None and self.real_backend_device == "cuda":
                with contextlib.suppress(Exception):
                    self._torch.cuda.empty_cache()

    def _wave_from_array(self, audio: Any, sample_rate: int) -> bytes:
        if self._np is None:
            raise EngineHTTPError(
                500,
                "REAL_BACKEND_INIT_FAILED",
                "numpy no disponible para serializar audio del backend real.",
            )

        np_mod = self._np
        if self._torch is not None and isinstance(audio, self._torch.Tensor):
            array = audio.detach().cpu().float().numpy()
        else:
            array = np_mod.asarray(audio, dtype=np_mod.float32)

        if array.ndim > 1:
            array = array[0]
        array = array.reshape(-1)
        array = np_mod.clip(array, -1.0, 1.0)
        pcm = (array * 32767.0).astype(np_mod.int16)

        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(pcm.tobytes())
        return buffer.getvalue()

    def _prepare_reference_audio_path(self, reference_audio: bytes, extension: str) -> Path:
        normalized_ext = extension.lower().strip() if extension else ".wav"
        if not normalized_ext.startswith("."):
            normalized_ext = f".{normalized_ext}"

        tmp_dir = self.data_dir / "tmp"
        tmp_dir.mkdir(parents=True, exist_ok=True)
        fd, raw_file = tempfile.mkstemp(prefix="ref_", suffix=normalized_ext, dir=str(tmp_dir))  # noqa: PTH123
        os.close(fd)
        raw_path = Path(raw_file)
        raw_path.write_bytes(reference_audio)

        if normalized_ext in {".wav", ".x-wav"}:
            return raw_path

        try:
            import librosa
            import soundfile as sf

            audio, _ = librosa.load(str(raw_path), sr=24000, mono=True)
            wav_path = raw_path.with_suffix(".wav")
            sf.write(str(wav_path), audio, 24000)
            raw_path.unlink(missing_ok=True)
            return wav_path
        except Exception as error:  # noqa: BLE001
            raw_path.unlink(missing_ok=True)
            raise EngineHTTPError(
                400,
                "INVALID_REFERENCE_AUDIO",
                f"No se pudo convertir el audio de referencia: {error}",
            ) from error

    @staticmethod
    def _validate_profile(profile: str) -> str:
        if profile not in MODEL_PROFILES:
            raise EngineHTTPError(400, "INVALID_PROFILE", f"Perfil desconocido: {profile}")
        return profile

    def _component_size(self, component: dict[str, Any]) -> int:
        if self.simulate_download:
            return int(component.get("simulated_size_bytes") or component["size_bytes"])
        return int(component["size_bytes"])

    def _profile_dir(self, profile: str) -> Path:
        return self.cache_dir / profile

    def _component_target(self, profile: str, component_name: str) -> Path:
        return self._profile_dir(profile) / component_name

    def _component_part_target(self, profile: str, component_name: str) -> Path:
        return self._profile_dir(profile) / f"{component_name}.part"

    def _components(self, profile: str) -> list[dict[str, Any]]:
        return MODEL_PROFILES[profile]["components"]

    def _profile_total_size(self, profile: str) -> int:
        return sum(self._component_size(component) for component in self._components(profile))

    def _profile_downloaded_bytes(self, profile: str) -> int:
        total = 0
        for component in self._components(profile):
            size_target = self._component_size(component)
            final_file = self._component_target(profile, component["name"])
            part_file = self._component_part_target(profile, component["name"])
            if final_file.exists():
                total += min(size_target, final_file.stat().st_size)
                continue
            if part_file.exists():
                total += min(size_target, part_file.stat().st_size)
        return total

    def is_profile_downloaded(self, profile: str) -> bool:
        profile = self._validate_profile(profile)
        if self.inference_backend == "chatterbox":
            return self.real_backend_cache_ready
        for component in self._components(profile):
            target = self._component_target(profile, component["name"])
            size_expected = self._component_size(component)
            if not target.exists() or target.stat().st_size < size_expected:
                return False
        return True

    def authorize(self, request: Request) -> None:
        if request.url.path in PUBLIC_PATHS:
            return

        origin = request.headers.get("origin")
        if origin and not self._is_origin_allowed(origin):
            raise EngineHTTPError(403, "ORIGIN_NOT_ALLOWED", "Origin no autorizado para este motor local.")

        authorization = request.headers.get("authorization", "")
        if not authorization.startswith("Bearer "):
            raise EngineHTTPError(401, "MISSING_TOKEN", "Falta token de autorizacion local.")
        token = authorization.replace("Bearer ", "", 1).strip()
        if token != self.api_token:
            raise EngineHTTPError(401, "INVALID_TOKEN", "Token local invalido.")

    def _is_origin_allowed(self, origin: str) -> bool:
        if origin in self.allowed_origins:
            return True
        if self.allowed_origin_pattern is None:
            return False
        return bool(self.allowed_origin_pattern.match(origin))

    def health_payload(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "service": DEFAULT_SERVICE_NAME,
            "token_required": True,
        }

    def version_payload(self) -> dict[str, Any]:
        return {"version": __version__}

    def capabilities_payload(self) -> dict[str, Any]:
        return {
            "platform": platform.platform(),
            "gpu_available": self.real_backend_available and self.real_backend_device != "cpu",
            "loaded_profile": self.loaded_profile,
            "profiles": list(MODEL_PROFILES.keys()),
            "simulate_download": self.simulate_download,
            "inference_backend": self.inference_backend,
            "backend_mode": self.backend_mode,
            "real_backend_available": self.real_backend_available,
            "real_backend_device": self.real_backend_device,
            "real_backend_error": self.real_backend_error,
            "allowed_origins": self.allowed_origins,
            "allowed_origin_regex": self.allowed_origin_regex,
        }

    def get_download_status(self, profile: str) -> dict[str, Any]:
        profile = self._validate_profile(profile)
        with self._lock:
            job = self.download_jobs.get(profile)
            if job:
                return job.to_payload()

        if self.inference_backend == "chatterbox":
            if self.real_backend_cache_ready:
                return DownloadJob(
                    profile=profile,
                    status="completed",
                    stage="completed",
                    progress=100.0,
                    downloaded_bytes=1,
                    total_bytes=1,
                    started_at=0,
                    updated_at=time.time(),
                ).to_payload()
            return DownloadJob(
                profile=profile,
                status="idle",
                stage="idle",
                progress=0.0,
                downloaded_bytes=0,
                total_bytes=1,
                started_at=0,
                updated_at=time.time(),
            ).to_payload()

        total = self._profile_total_size(profile)
        downloaded = self._profile_downloaded_bytes(profile)
        if downloaded >= total and total > 0:
            return DownloadJob(
                profile=profile,
                status="completed",
                stage="completed",
                progress=100.0,
                downloaded_bytes=total,
                total_bytes=total,
                started_at=0,
                updated_at=time.time(),
            ).to_payload()

        progress = (downloaded / total * 100.0) if total else 0.0
        return DownloadJob(
            profile=profile,
            status="idle",
            stage="idle",
            progress=progress,
            downloaded_bytes=downloaded,
            total_bytes=total,
            started_at=0,
            updated_at=time.time(),
        ).to_payload()

    def start_download(self, profile: str) -> dict[str, Any]:
        profile = self._validate_profile(profile)
        if self.is_profile_downloaded(profile):
            payload = self.get_download_status(profile)
            self.log(f"Perfil {profile} ya esta descargado.")
            return payload

        if self.inference_backend == "chatterbox":
            with self._lock:
                current = self.download_jobs.get(profile)
                if current and current.status == "downloading":
                    return current.to_payload()

                now = time.time()
                job = DownloadJob(
                    profile=profile,
                    status="downloading",
                    stage="queued",
                    progress=5.0,
                    downloaded_bytes=0,
                    total_bytes=1,
                    started_at=now,
                    updated_at=now,
                )
                self.download_jobs[profile] = job
                thread = threading.Thread(target=self._prefetch_real_model_worker, args=(profile,), daemon=True)
                self.download_threads[profile] = thread
                thread.start()
            self.log(f"Descarga iniciada para perfil {profile} (backend chatterbox).")
            return job.to_payload()

        with self._lock:
            current = self.download_jobs.get(profile)
            if current and current.status == "downloading":
                return current.to_payload()

            now = time.time()
            total = self._profile_total_size(profile)
            downloaded = self._profile_downloaded_bytes(profile)
            job = DownloadJob(
                profile=profile,
                status="downloading",
                stage="downloading",
                progress=(downloaded / total * 100.0) if total else 0.0,
                downloaded_bytes=downloaded,
                total_bytes=total,
                started_at=now,
                updated_at=now,
            )
            self.download_jobs[profile] = job

            thread = threading.Thread(target=self._download_worker, args=(profile,), daemon=True)
            self.download_threads[profile] = thread
            thread.start()

        self.log(f"Descarga iniciada para perfil {profile}.")
        return job.to_payload()

    def _prefetch_real_model_worker(self, profile: str) -> None:
        try:
            with self._lock:
                job = self.download_jobs[profile]
                job.progress = 15.0
                job.stage = "initializing_backend"
                job.updated_at = time.time()
            self.log("Fase Pro: inicializando backend real y resolviendo checkpoints de HuggingFace...")
            self._ensure_real_backend_model()
            with self._lock:
                job = self.download_jobs[profile]
                job.status = "completed"
                job.stage = "completed"
                job.progress = 100.0
                job.downloaded_bytes = 1
                job.total_bytes = 1
                job.error = None
                job.updated_at = time.time()
            self.log(f"Descarga completada para perfil {profile} (cache real lista).")
        except Exception as error:  # noqa: BLE001
            detail = f"{type(error).__name__}: {error}"
            with self._lock:
                job = self.download_jobs[profile]
                job.status = "failed"
                job.stage = "failed"
                job.error = detail
                job.updated_at = time.time()
            self.real_backend_error = str(error)
            self.log(f"Descarga fallo para perfil {profile}: {detail}")
            self.log(traceback.format_exc())

    def _download_worker(self, profile: str) -> None:
        try:
            profile_dir = self._profile_dir(profile)
            profile_dir.mkdir(parents=True, exist_ok=True)

            for component in self._components(profile):
                self._download_component(profile, component)

            with self._lock:
                job = self.download_jobs[profile]
                job.status = "completed"
                job.stage = "completed"
                job.progress = 100.0
                job.downloaded_bytes = job.total_bytes
                job.error = None
                job.updated_at = time.time()
            self.log(f"Descarga completada para perfil {profile}.")
        except Exception as error:  # noqa: BLE001
            detail = f"{type(error).__name__}: {error}"
            with self._lock:
                job = self.download_jobs[profile]
                job.status = "failed"
                job.stage = "failed"
                job.error = detail
                job.updated_at = time.time()
            self.log(f"Descarga fallo para perfil {profile}: {detail}")
            self.log(traceback.format_exc())

    def _download_component(self, profile: str, component: dict[str, Any]) -> None:
        component_name = str(component["name"])
        target_size = self._component_size(component)
        target = self._component_target(profile, component_name)
        part = self._component_part_target(profile, component_name)

        if target.exists() and target.stat().st_size >= target_size:
            return

        if self.simulate_download or not component.get("url"):
            current_size = part.stat().st_size if part.exists() else 0
            with open(part, "ab") as stream:
                while current_size < target_size:
                    chunk_size = min(DOWNLOAD_CHUNK_BYTES, target_size - current_size)
                    stream.write(b"\0" * chunk_size)
                    current_size += chunk_size
                    self._update_download_progress(profile, chunk_size)
                    time.sleep(DOWNLOAD_SLEEP_SECONDS)
            part.replace(target)
            self._write_checksum(target)
            return

        self._http_download_component(profile, component, target, part, target_size)

    def _http_download_component(
        self,
        profile: str,
        component: dict[str, Any],
        target: Path,
        part: Path,
        target_size: int,
    ) -> None:
        url = str(component["url"])
        part.parent.mkdir(parents=True, exist_ok=True)
        downloaded = part.stat().st_size if part.exists() else 0

        headers: dict[str, str] = {}
        if downloaded > 0:
            headers["Range"] = f"bytes={downloaded}-"

        with requests.get(url, stream=True, timeout=30, headers=headers) as response:
            response.raise_for_status()

            if downloaded > 0 and response.status_code == 200:
                part.unlink(missing_ok=True)
                downloaded = 0

            with open(part, "ab") as stream:
                for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_BYTES):
                    if not chunk:
                        continue
                    stream.write(chunk)
                    downloaded += len(chunk)
                    self._update_download_progress(profile, len(chunk))

        final_size = part.stat().st_size
        if final_size < target_size:
            raise EngineHTTPError(
                500,
                "DOWNLOAD_INCOMPLETE",
                f"Descarga incompleta para {target.name} ({final_size}/{target_size}).",
            )
        part.replace(target)
        self._write_checksum(target)

    def _write_checksum(self, target: Path) -> None:
        hasher = hashlib.sha256()
        with open(target, "rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(chunk)
        checksum_path = target.with_suffix(f"{target.suffix}.sha256")
        checksum_path.write_text(hasher.hexdigest(), encoding="utf-8")

    def _update_download_progress(self, profile: str, bytes_delta: int) -> None:
        with self._lock:
            job = self.download_jobs[profile]
            job.downloaded_bytes = min(job.total_bytes, job.downloaded_bytes + bytes_delta)
            if job.total_bytes > 0:
                job.progress = job.downloaded_bytes / job.total_bytes * 100.0
            job.updated_at = time.time()

    def load_model(self, profile: str) -> dict[str, Any]:
        profile = self._validate_profile(profile)
        if self.inference_backend != "chatterbox" and not self.is_profile_downloaded(profile):
            raise EngineHTTPError(409, "MODEL_NOT_DOWNLOADED", "Modelo no descargado. Ejecuta /models/download.")

        with self._lock:
            if profile in self.loading_profiles:
                raise EngineHTTPError(409, "MODEL_LOADING", "El modelo ya se esta cargando.")
            self.loading_profiles.add(profile)

        try:
            self.log(f"Cargando perfil {profile} en memoria...")
            if self.inference_backend == "chatterbox":
                self._ensure_real_backend_model()
                self.real_backend_cache_ready = True
            else:
                time.sleep(1.0)

            with self._lock:
                self.loaded_profile = profile
                self._save_state()

            self.log(f"Perfil {profile} cargado.")
            return {"status": "loaded", "profile": profile}
        finally:
            with self._lock:
                self.loading_profiles.discard(profile)

    def unload_model(self, profile: str) -> dict[str, Any]:
        profile = self._validate_profile(profile)
        with self._lock:
            if self.loaded_profile == profile:
                self.loaded_profile = None
                self._save_state()
                if self.inference_backend == "chatterbox" and RELEASE_MODEL_ON_UNLOAD:
                    self._release_real_backend_model()
                self.log(f"Perfil {profile} descargado de memoria.")
                return {"status": "unloaded", "profile": profile}
        return {"status": "noop", "profile": profile}

    def _synthesize_wave(self, text: str, sample_rate: int, voice_bias_hz: float = 0.0) -> bytes:
        duration_seconds = max(1.2, min(14.0, 0.06 * len(text) + 1.0))
        total_samples = int(sample_rate * duration_seconds)
        data = bytearray()

        base_frequency = 170.0 + voice_bias_hz
        for index in range(total_samples):
            timestamp = index / sample_rate
            fade = min(1.0, index / (sample_rate * 0.08))
            fade_out = min(1.0, (total_samples - index) / (sample_rate * 0.08))
            env = max(0.0, min(fade, fade_out))
            carrier = math.sin(2.0 * math.pi * base_frequency * timestamp)
            mod = 0.25 * math.sin(2.0 * math.pi * 4.0 * timestamp)
            sample = 0.28 * env * carrier * (1.0 + mod)
            pcm = int(max(-1.0, min(1.0, sample)) * 32767)
            data.extend(struct.pack("<h", pcm))

        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(bytes(data))
        return buffer.getvalue()

    @staticmethod
    def _voice_bias(reference_audio: bytes) -> float:
        sample = reference_audio[:4096]
        digest = hashlib.sha256(sample).digest()
        value = int.from_bytes(digest[:2], byteorder="big", signed=False)
        return (value % 60) - 30.0

    def tts(self, text: str, profile: str, _language: str) -> bytes:
        profile = self._validate_profile(profile)
        if self.loaded_profile != profile:
            raise EngineHTTPError(409, "MODEL_NOT_LOADED", "El perfil solicitado no esta cargado.")
        if self.inference_backend == "chatterbox":
            self._ensure_real_backend_model()
            try:
                assert self._real_model is not None
                sample_rate = int(getattr(self._real_model, "sr", 24000))
                wav = self._real_model.generate(text, language_id=_language)
                return self._wave_from_array(wav, sample_rate)
            except EngineHTTPError:
                raise
            except Exception as error:  # noqa: BLE001
                raise EngineHTTPError(500, "INFERENCE_FAILED", str(error)) from error
        return self._synthesize_wave(text=text, sample_rate=24000, voice_bias_hz=0.0)

    def clone(
        self,
        text: str,
        profile: str,
        _language: str,
        reference_audio: bytes,
        reference_extension: str,
    ) -> bytes:
        profile = self._validate_profile(profile)
        if self.loaded_profile != profile:
            raise EngineHTTPError(409, "MODEL_NOT_LOADED", "El perfil solicitado no esta cargado.")
        if len(reference_audio) < 1024:
            raise EngineHTTPError(400, "INVALID_REFERENCE_AUDIO", "El audio de referencia es demasiado corto.")
        if self.inference_backend == "chatterbox":
            self._ensure_real_backend_model()
            reference_path = self._prepare_reference_audio_path(reference_audio, reference_extension)
            try:
                assert self._real_model is not None
                sample_rate = int(getattr(self._real_model, "sr", 24000))
                wav = self._real_model.generate(
                    text,
                    language_id=_language,
                    audio_prompt_path=str(reference_path),
                )
                return self._wave_from_array(wav, sample_rate)
            except EngineHTTPError:
                raise
            except Exception as error:  # noqa: BLE001
                raise EngineHTTPError(500, "INFERENCE_FAILED", str(error)) from error
            finally:
                reference_path.unlink(missing_ok=True)
        bias = self._voice_bias(reference_audio)
        return self._synthesize_wave(text=text, sample_rate=24000, voice_bias_hz=bias)


class PrivateNetworkAccessMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Any]) -> Any:
        response = await call_next(request)
        if request.headers.get("access-control-request-private-network", "").lower() == "true":
            response.headers["Access-Control-Allow-Private-Network"] = "true"
        return response


def create_app(runtime: EngineRuntime) -> FastAPI:
    app = FastAPI(title="Studio Voice Local Engine", version=__version__)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=runtime.allowed_origins,
        allow_origin_regex=runtime.allowed_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(PrivateNetworkAccessMiddleware)

    @app.exception_handler(EngineHTTPError)
    async def handle_engine_error(_: Request, error: EngineHTTPError) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content={"error": {"code": error.code, "message": error.message}},
        )

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return runtime.health_payload()

    @app.get("/version")
    async def version() -> dict[str, Any]:
        return runtime.version_payload()

    @app.get("/capabilities")
    async def capabilities(request: Request) -> dict[str, Any]:
        runtime.authorize(request)
        return runtime.capabilities_payload()

    @app.post("/models/download")
    async def models_download(request: Request, body: DownloadRequest) -> dict[str, Any]:
        runtime.authorize(request)
        return runtime.start_download(body.profile)

    @app.get("/models/download/status")
    async def models_download_status(request: Request, profile: str = PRO_PROFILE) -> dict[str, Any]:
        runtime.authorize(request)
        return runtime.get_download_status(profile)

    @app.post("/models/load")
    async def models_load(request: Request, body: LoadRequest) -> dict[str, Any]:
        runtime.authorize(request)
        return runtime.load_model(body.profile)

    @app.post("/models/unload")
    async def models_unload(request: Request, body: LoadRequest) -> dict[str, Any]:
        runtime.authorize(request)
        return runtime.unload_model(body.profile)

    @app.post("/tts")
    async def tts(request: Request, body: TTSRequest) -> StreamingResponse:
        runtime.authorize(request)
        started_at = time.perf_counter()
        wav_bytes = runtime.tts(body.text, body.quality_profile, body.language)
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        headers = {
            "X-Engine-Mode": "pro-local",
            "X-Model-Profile": body.quality_profile,
            "X-Latency-Ms": str(elapsed_ms),
        }
        return StreamingResponse(io.BytesIO(wav_bytes), media_type="audio/wav", headers=headers)

    @app.post("/clone")
    async def clone(
        request: Request,
        text: str = Form(...),
        language: str = Form("es"),
        quality_profile: str = Form(PRO_PROFILE),
        reference_audio: UploadFile = File(...),
    ) -> StreamingResponse:
        runtime.authorize(request)
        filename = reference_audio.filename or ""
        extension = Path(filename).suffix.lower()
        if extension not in {".wav", ".mp3", ".mpeg", ".x-wav"}:
            raise EngineHTTPError(400, "INVALID_REFERENCE_AUDIO", "Formato no soportado. Usa WAV o MP3.")

        payload = await reference_audio.read()
        started_at = time.perf_counter()
        wav_bytes = runtime.clone(text, quality_profile, language, payload, extension)
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        headers = {
            "X-Engine-Mode": "pro-local",
            "X-Model-Profile": quality_profile,
            "X-Latency-Ms": str(elapsed_ms),
        }
        return StreamingResponse(io.BytesIO(wav_bytes), media_type="audio/wav", headers=headers)

    return app


def main() -> None:
    import uvicorn

    runtime = EngineRuntime()
    app = create_app(runtime)
    uvicorn.run(app, host=DEFAULT_HOST, port=DEFAULT_PORT, log_level="info")


if __name__ == "__main__":
    main()
