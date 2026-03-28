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
import sys
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
DEFAULT_CONFIG_PATH = DEFAULT_DATA_DIR / "config.json"
DEFAULT_ALLOWED_ORIGINS = os.getenv(
    "LOCAL_ENGINE_ALLOWED_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173,https://your-railway-domain.railway.app",
)
DEFAULT_ALLOWED_ORIGIN_REGEX = os.getenv(
    "LOCAL_ENGINE_ALLOWED_ORIGIN_REGEX",
    r"^https://[a-z0-9-]+(\.up)?\.railway\.app$|^http://localhost(:\d+)?$|^http://127\.0\.0\.1(:\d+)?$",
)
SIMULATE_DOWNLOAD = os.getenv("SIMULATE_MODEL_DOWNLOAD", "0") != "0"
INFERENCE_BACKEND = os.getenv("LOCAL_ENGINE_INFERENCE_BACKEND", "auto").strip().lower()
RELEASE_MODEL_ON_UNLOAD = os.getenv("LOCAL_ENGINE_RELEASE_MODEL_ON_UNLOAD", "1") != "0"
REQUIRE_GPU = os.getenv("LOCAL_ENGINE_REQUIRE_GPU", "0") == "1"
GPU_DEVICE_POLICY = os.getenv("LOCAL_ENGINE_GPU_DEVICE_POLICY", "auto").strip().lower()
GPU_DEVICE_INDEX = os.getenv("LOCAL_ENGINE_CUDA_DEVICE_INDEX", "").strip()
RESPECT_CUDA_VISIBLE_DEVICES = os.getenv("LOCAL_ENGINE_RESPECT_CUDA_VISIBLE_DEVICES", "0") == "1"
PIN_FIRST_CUDA_DEVICE = os.getenv("LOCAL_ENGINE_PIN_FIRST_CUDA_DEVICE", "1") != "0"
ALLOW_FROZEN_CUDA = os.getenv("LOCAL_ENGINE_ALLOW_FROZEN_CUDA", "0") == "1"
ALLOW_FROZEN_REAL_BACKEND = os.getenv("LOCAL_ENGINE_ALLOW_FROZEN_REAL_BACKEND", "0") == "1"
DOWNLOAD_CHUNK_BYTES = 1024 * 512
DOWNLOAD_SLEEP_SECONDS = 0.015
EVENT_BUFFER_LIMIT = int(os.getenv("LOCAL_ENGINE_EVENT_BUFFER_LIMIT", "6000"))
EVENT_POLL_MAX_LIMIT = int(os.getenv("LOCAL_ENGINE_EVENT_POLL_MAX_LIMIT", "500"))
SAMPLING_LOG_STEP_PERCENT = float(os.getenv("LOCAL_ENGINE_SAMPLING_LOG_STEP_PERCENT", "2.0"))
MAX_REFERENCE_AUDIO_BYTES = int(os.getenv("LOCAL_ENGINE_MAX_REFERENCE_AUDIO_BYTES", str(20 * 1024 * 1024)))
MAX_REFERENCE_AUDIO_SECONDS = float(os.getenv("LOCAL_ENGINE_MAX_REFERENCE_AUDIO_SECONDS", "30.0"))
MAX_SEGMENT_CHARS = int(os.getenv("LOCAL_ENGINE_MAX_SEGMENT_CHARS", "300"))
SEGMENT_GAP_MS = int(os.getenv("LOCAL_ENGINE_SEGMENT_GAP_MS", "160"))
DEFAULT_CFG_WEIGHT = float(os.getenv("LOCAL_ENGINE_DEFAULT_CFG_WEIGHT", "0.5"))
DEFAULT_EXAGGERATION = float(os.getenv("LOCAL_ENGINE_DEFAULT_EXAGGERATION", "0.5"))
DEFAULT_TEMPERATURE = float(os.getenv("LOCAL_ENGINE_DEFAULT_TEMPERATURE", "0.8"))
MIN_CFG_WEIGHT = 0.0
MAX_CFG_WEIGHT = 1.5
MIN_EXAGGERATION = 0.0
MAX_EXAGGERATION = 2.0
MIN_TEMPERATURE = 0.1
MAX_TEMPERATURE = 2.0
MIN_SEED = 0
MAX_SEED = 2_147_483_647
PUBLIC_PATHS = {"/health", "/version", "/docs", "/openapi.json", "/redoc"}
PRO_PROFILE = "pro_multilingual_balanced"
DEFAULT_REFERENCE_PROMPTS: dict[str, dict[str, str]] = {
    "es": {
        "filename": "es_f1.flac",
        "url": "https://storage.googleapis.com/chatterbox-demo-samples/mtl_prompts/es_f1.flac",
        "label": "official_es_f1",
    },
    "en": {
        "filename": "en_f1.flac",
        "url": "https://storage.googleapis.com/chatterbox-demo-samples/mtl_prompts/en_f1.flac",
        "label": "official_en_f1",
    },
}

MODEL_PROFILES: dict[str, dict[str, Any]] = {
    PRO_PROFILE: {
        "display_name": "Chatterbox multilingual balanced (ES/EN)",
        "languages": ["es", "en"],
        "source_model": "resemble-ai/chatterbox",
        "components": [],
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
    request_id: str | None = Field(default=None, max_length=128)
    use_default_reference: bool = Field(default=True)
    cfg_weight: float | None = Field(default=None)
    exaggeration: float | None = Field(default=None)
    temperature: float | None = Field(default=None)
    seed: int | None = Field(default=None)


async def _read_upload_bytes_limited(upload: UploadFile, *, max_bytes: int) -> bytes:
    data = bytearray()
    try:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > max_bytes:
                max_mb = max(1, math.ceil(max_bytes / (1024 * 1024)))
                raise EngineHTTPError(
                    413,
                    "REFERENCE_AUDIO_TOO_LARGE",
                    (
                        f"El audio de referencia supera el limite de {max_mb} MB. "
                        "Usa un clip corto de 5-30 segundos."
                    ),
                )
        return bytes(data)
    finally:
        with contextlib.suppress(Exception):
            await upload.close()


class EngineRuntime:
    def __init__(self, logger: Callable[[str], None] | None = None) -> None:
        self.log = logger if logger is not None else lambda msg: None
        self.data_dir = DEFAULT_DATA_DIR
        self.cache_dir = self.data_dir / "cache"
        self.prompts_dir = self.data_dir / "default_prompts"
        self.state_path = self.data_dir / "state.json"
        self.token_path = self.data_dir / "api_token.txt"
        self.config_path = DEFAULT_CONFIG_PATH
        self.simulate_download = SIMULATE_DOWNLOAD

        self._lock = threading.Lock()
        self.download_jobs: dict[str, DownloadJob] = {}
        self.download_threads: dict[str, threading.Thread] = {}
        self.loading_profiles: set[str] = set()
        self.loaded_profile: str | None = None
        self.backend_lock = threading.Lock()
        self.events_lock = threading.Lock()
        self.events_cursor = 0
        self.events: list[dict[str, Any]] = []
        self.last_sampling_progress: dict[str, float] = {}

        # Real-inference backend state (Chatterbox runtime).
        self.inference_backend = "mock"
        self.backend_mode = INFERENCE_BACKEND
        self.real_backend_available = False
        self.real_backend_error: str | None = None
        self.real_backend_device = "cpu"
        self.real_backend_device_reason = "uninitialized"
        self.real_backend_cuda_index: int | None = None
        self.real_backend_cuda_devices: list[dict[str, Any]] = []
        self.real_backend_torch_info: dict[str, Any] = {}
        self.real_backend_cache_ready = False
        self._torch: Any | None = None
        self._np: Any | None = None
        self._chatterbox_class: Any | None = None
        self._real_model: Any | None = None

        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.prompts_dir.mkdir(parents=True, exist_ok=True)
        self.runtime_config = self._load_runtime_config()
        self.allowed_origins = self._resolve_allowed_origins()
        self.allowed_origin_regex = self._resolve_allowed_origin_regex()
        self.allowed_origin_pattern = re.compile(self.allowed_origin_regex) if self.allowed_origin_regex else None
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

    def _load_runtime_config(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return {}
        try:
            payload = json.loads(self.config_path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError:
            self.log("WARN: config.json no es JSON valido. Se usaran valores por defecto.")
            return {}
        if not isinstance(payload, dict):
            self.log("WARN: config.json no tiene un objeto valido. Se usaran valores por defecto.")
            return {}
        return payload

    def _resolve_allowed_origins(self) -> list[str]:
        configured = self.runtime_config.get("allowed_origins")
        if isinstance(configured, list):
            values = [str(item).strip() for item in configured if str(item).strip()]
            if values:
                return values
        return [origin.strip() for origin in DEFAULT_ALLOWED_ORIGINS.split(",") if origin.strip()]

    def _resolve_allowed_origin_regex(self) -> str | None:
        configured = self.runtime_config.get("allowed_origin_regex")
        if isinstance(configured, str) and configured.strip():
            return configured.strip()
        return DEFAULT_ALLOWED_ORIGIN_REGEX.strip() or None

    def _runtime_class(self) -> str:
        if self.inference_backend == "chatterbox":
            if str(self.real_backend_device).startswith("cuda") or self.real_backend_device == "mps":
                return "real_gpu"
            return "real_cpu"
        if self.real_backend_device_reason == "frozen_real_backend_disabled_default":
            return "disabled_frozen"
        return "mock"

    def _quality_tier(self) -> str:
        runtime_class = self._runtime_class()
        if runtime_class == "real_gpu":
            return "pro_real"
        if runtime_class == "real_cpu":
            return "degraded_cpu"
        if runtime_class == "disabled_frozen":
            return "disabled_frozen"
        return "compatible_mock"

    @staticmethod
    def _bytes_to_mib(value: int | None) -> str:
        if value is None or value <= 0:
            return "n/a"
        return f"{value / (1024 * 1024):.0f} MiB"

    @staticmethod
    def _parse_cuda_index(raw_value: str) -> int | None:
        value = raw_value.strip()
        if not value:
            return None
        try:
            index = int(value)
        except ValueError:
            return None
        return index if index >= 0 else None

    def _collect_torch_diagnostics(self, torch_mod: Any) -> None:
        torch_version = str(getattr(torch_mod, "__version__", "unknown"))
        cuda_build = str(getattr(getattr(torch_mod, "version", None), "cuda", None) or "")
        cuda_visible_devices = os.getenv("CUDA_VISIBLE_DEVICES")
        cuda_available = False
        device_count = 0
        devices: list[dict[str, Any]] = []
        supported_arches: list[str] = []

        try:
            cuda_available = bool(torch_mod.cuda.is_available())
        except Exception as error:  # noqa: BLE001
            self.log(f"WARN: torch.cuda.is_available() fallo: {error}")

        try:
            if cuda_available:
                device_count = int(torch_mod.cuda.device_count())
        except Exception as error:  # noqa: BLE001
            self.log(f"WARN: torch.cuda.device_count() fallo: {error}")

        try:
            if cuda_available:
                supported_arches = [str(item) for item in torch_mod.cuda.get_arch_list()]
        except Exception as error:  # noqa: BLE001
            self.log(f"WARN: torch.cuda.get_arch_list() fallo: {error}")

        for index in range(device_count):
            device_info: dict[str, Any] = {"index": index}
            try:
                props = torch_mod.cuda.get_device_properties(index)
                total_memory = int(getattr(props, "total_memory", 0) or 0)
                major = getattr(props, "major", None)
                minor = getattr(props, "minor", None)
                capability = f"{major}.{minor}" if major is not None and minor is not None else "n/a"
                capability_sm = f"sm_{major}{minor}" if major is not None and minor is not None else ""
                supported_by_build = bool(capability_sm and capability_sm in supported_arches) if supported_arches else True
                device_info.update(
                    {
                        "name": str(getattr(props, "name", f"cuda:{index}")),
                        "total_memory_bytes": total_memory,
                        "capability": capability,
                        "capability_sm": capability_sm,
                        "supported_by_build": supported_by_build,
                    }
                )
            except Exception as error:  # noqa: BLE001
                device_info.update(
                    {
                        "name": f"cuda:{index}",
                        "total_memory_bytes": 0,
                        "capability": "unknown",
                        "error": str(error),
                    }
                )
            devices.append(device_info)

        self.real_backend_torch_info = {
            "torch_version": torch_version,
            "torch_cuda_build": cuda_build,
            "cuda_visible_devices": cuda_visible_devices,
            "cuda_available": cuda_available,
            "cuda_device_count": device_count,
            "cuda_supported_arches": supported_arches,
        }
        self.real_backend_cuda_devices = devices

        self.log(
            "Torch diagnostics: "
            f"torch={torch_version}, "
            f"cuda_build={cuda_build or 'none'}, "
            f"CUDA_VISIBLE_DEVICES={cuda_visible_devices or 'not-set'}, "
            f"cuda_available={cuda_available}, "
            f"cuda_device_count={device_count}."
        )
        if devices:
            for device in devices:
                label = f"cuda:{device['index']} {device.get('name', 'unknown')}"
                self.log(
                    f"GPU detectada -> {label}, "
                    f"VRAM={self._bytes_to_mib(int(device.get('total_memory_bytes', 0) or 0))}, "
                    f"capability={device.get('capability', 'n/a')}, "
                    f"supported_by_build={device.get('supported_by_build', True)}."
                )
        else:
            self.log("No se detectaron dispositivos CUDA utilizables para inferencia.")

    def _select_cuda_device(self) -> tuple[str, str, int | None]:
        if not self.real_backend_cuda_devices:
            return "cpu", "cuda_not_available", None

        supported_devices = [item for item in self.real_backend_cuda_devices if bool(item.get("supported_by_build", True))]
        if not supported_devices:
            return "cpu", "cuda_devices_incompatible_with_torch_build", None

        forced_index = self._parse_cuda_index(GPU_DEVICE_INDEX)
        if forced_index is not None:
            matched = next((item for item in supported_devices if int(item["index"]) == forced_index), None)
            if matched is not None:
                return f"cuda:{forced_index}", f"forced_by_env:{forced_index}", forced_index
            if forced_index < len(self.real_backend_cuda_devices):
                return "cpu", f"forced_gpu_incompatible:{forced_index}", None
            self.log(
                f"WARN: LOCAL_ENGINE_CUDA_DEVICE_INDEX={forced_index} fuera de rango "
                f"(0-{len(self.real_backend_cuda_devices) - 1}). Se aplicara seleccion automatica."
            )

        policy = GPU_DEVICE_POLICY if GPU_DEVICE_POLICY in {"auto", "max_vram", "first"} else "auto"
        if policy == "first":
            return "cuda:0", "policy:first", 0

        # auto/max_vram: prefer the GPU with more VRAM (typical best default in multi-GPU desktops).
        best = max(
            supported_devices,
            key=lambda item: int(item.get("total_memory_bytes", 0) or 0),
        )
        selected_index = int(best["index"])
        return f"cuda:{selected_index}", f"policy:max_vram(cuda:{selected_index})", selected_index

    def _init_inference_backend(self) -> None:
        mode = self.backend_mode
        if mode not in {"auto", "mock", "chatterbox"}:
            self.log(f"LOCAL_ENGINE_INFERENCE_BACKEND invalido ({mode}), usando auto.")
            mode = "auto"
            self.backend_mode = "auto"

        is_frozen_runtime = bool(getattr(sys, "frozen", False))
        if is_frozen_runtime and not ALLOW_FROZEN_REAL_BACKEND and mode in {"auto", "chatterbox"}:
            self.inference_backend = "mock"
            self.real_backend_available = False
            self.real_backend_device = "cpu"
            self.real_backend_device_reason = "frozen_real_backend_disabled_default"
            self.real_backend_error = (
                "Backend real desactivado por estabilidad en .exe empaquetado. "
                "Usa run_local_engine.bat o exporta LOCAL_ENGINE_ALLOW_FROZEN_REAL_BACKEND=1."
            )
            self.real_backend_torch_info = {
                "torch_version": None,
                "torch_cuda_build": None,
                "cuda_visible_devices": os.getenv("CUDA_VISIBLE_DEVICES"),
                "cuda_available": False,
                "cuda_device_count": 0,
                "cuda_supported_arches": [],
            }
            self.real_backend_cuda_devices = []
            self.log(
                "WARN: backend real desactivado por estabilidad en runtime empaquetado (.exe). "
                "Se usara mock para evitar crashes nativos (c10.dll). "
                "Si quieres forzar backend real, exporta LOCAL_ENGINE_ALLOW_FROZEN_REAL_BACKEND=1."
            )
            return

        if mode == "mock":
            self.inference_backend = "mock"
            self.log("Backend de inferencia: mock (audio sintetico).")
            return

        inherited_cuda_visible = os.getenv("CUDA_VISIBLE_DEVICES")
        if not RESPECT_CUDA_VISIBLE_DEVICES:
            if inherited_cuda_visible:
                normalized_visible = inherited_cuda_visible.strip()
                if normalized_visible != "0":
                    self.log(
                        f"Detectado CUDA_VISIBLE_DEVICES={inherited_cuda_visible}. "
                        "Se forzara CUDA_VISIBLE_DEVICES=0 para evitar crash en configuraciones multi-GPU "
                        "(usa LOCAL_ENGINE_RESPECT_CUDA_VISIBLE_DEVICES=1 para conservar el valor original)."
                    )
                    os.environ["CUDA_VISIBLE_DEVICES"] = "0"
                else:
                    self.log("Detectado CUDA_VISIBLE_DEVICES=0. Se conserva por estabilidad.")
            elif PIN_FIRST_CUDA_DEVICE:
                os.environ["CUDA_VISIBLE_DEVICES"] = "0"
                self.log(
                    "No se detecto CUDA_VISIBLE_DEVICES. "
                    "Se fija CUDA_VISIBLE_DEVICES=0 por estabilidad en equipos multi-GPU "
                    "(desactiva con LOCAL_ENGINE_PIN_FIRST_CUDA_DEVICE=0)."
                )

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
            self._collect_torch_diagnostics(torch)

            if self.real_backend_torch_info.get("cuda_available"):
                if is_frozen_runtime and not ALLOW_FROZEN_CUDA:
                    self.real_backend_device = "cpu"
                    self.real_backend_device_reason = "frozen_cuda_disabled_default"
                    self.real_backend_cuda_index = None
                    self.log(
                        "WARN: runtime empaquetado (.exe) detectado. "
                        "CUDA se desactiva por estabilidad para evitar crashes nativos. "
                        "Si quieres forzar GPU en .exe, exporta LOCAL_ENGINE_ALLOW_FROZEN_CUDA=1."
                    )
                else:
                    device, reason, cuda_index = self._select_cuda_device()
                    self.real_backend_device = device
                    self.real_backend_device_reason = reason
                    self.real_backend_cuda_index = cuda_index
                    if device == "cpu":
                        self.log(
                            "WARN: CUDA detectado, pero no hay GPU compatible con este build de torch. "
                            "Se usara CPU para evitar crash del backend."
                        )
            elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
                self.real_backend_device = "mps"
                self.real_backend_device_reason = "mps_available"
            else:
                self.real_backend_device = "cpu"
                cuda_build = str(self.real_backend_torch_info.get("torch_cuda_build") or "")
                if not cuda_build:
                    self.real_backend_device_reason = "torch_without_cuda_build"
                    self.log(
                        "WARN: torch instalado sin CUDA. Si tienes GPU NVIDIA y quieres usarla, "
                        "instala wheels CUDA: "
                        "python -m pip install --upgrade --index-url https://download.pytorch.org/whl/cu124 "
                        "torch==2.6.0 torchaudio==2.6.0"
                    )
                else:
                    self.real_backend_device_reason = "cuda_runtime_unavailable"

            self.inference_backend = "chatterbox"
            self.log(
                "Backend de inferencia: "
                f"chatterbox ({self.real_backend_device}) "
                f"[reason={self.real_backend_device_reason}]."
            )
        except Exception as error:  # noqa: BLE001
            self.real_backend_available = False
            self.real_backend_error = str(error)
            self.real_backend_device_reason = "backend_init_exception"
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
                if target_device.type == "cuda" and target_device.index is not None:
                    with contextlib.suppress(Exception):
                        torch_mod.cuda.set_device(target_device.index)
                        self.log(f"CUDA device activo fijado en cuda:{target_device.index}.")
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
                raise self._map_backend_init_exception(error) from error

    @staticmethod
    def _map_backend_init_exception(error: Exception) -> EngineHTTPError:
        detail = str(error)
        normalized = detail.lower()
        winerror = getattr(error, "winerror", None)
        if (
            winerror == 1455
            or "os error 1455" in normalized
            or "archivo de paginaci" in normalized
            or "paging file" in normalized
        ):
            return EngineHTTPError(
                507,
                "INSUFFICIENT_VIRTUAL_MEMORY",
                (
                    "Windows no tiene memoria virtual suficiente para cargar el modelo Pro "
                    "(pagefile insuficiente). Cierra apps pesadas, reinicia el PC y aumenta "
                    "la memoria virtual en Configuracion avanzada del sistema > Rendimiento "
                    "> Memoria virtual."
                ),
            )
        return EngineHTTPError(500, "REAL_BACKEND_INIT_FAILED", detail)

    def _fallback_to_mock_runtime(self, error: EngineHTTPError) -> bool:
        if self.backend_mode != "auto":
            return False
        if error.code not in {"INSUFFICIENT_VIRTUAL_MEMORY", "REAL_BACKEND_INIT_FAILED"}:
            return False
        self.real_backend_available = False
        self.real_backend_error = error.message
        self.inference_backend = "mock"
        self._real_model = None
        self.log(
            "WARN: recursos insuficientes para backend real. "
            "Se activa modo compatible (mock) para mantener el motor funcional."
        )
        return True

    def _release_real_backend_model(self) -> None:
        with self.backend_lock:
            self._real_model = None
            if self._torch is not None and str(self.real_backend_device).startswith("cuda"):
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

        try:
            import librosa
            import soundfile as sf

            audio, sample_rate = librosa.load(str(raw_path), sr=24000, mono=True)
            if audio.size == 0:
                raise EngineHTTPError(400, "INVALID_REFERENCE_AUDIO", "El audio de referencia esta vacio.")

            duration_seconds = float(audio.shape[0]) / float(sample_rate)
            if duration_seconds < 1.5:
                raise EngineHTTPError(
                    400,
                    "INVALID_REFERENCE_AUDIO",
                    "El audio de referencia es demasiado corto. Usa una muestra limpia de 3 a 10 segundos.",
                )

            with contextlib.suppress(Exception):
                trimmed_audio, _ = librosa.effects.trim(audio, top_db=30)
                if trimmed_audio.size > 0:
                    audio = trimmed_audio

            max_samples = max(1, int(sample_rate * MAX_REFERENCE_AUDIO_SECONDS))
            if audio.shape[0] > max_samples:
                audio = audio[:max_samples]

            peak = float(max(abs(float(audio.min())), abs(float(audio.max())))) if audio.size else 0.0
            if peak > 0.0:
                audio = audio / peak * 0.97

            wav_fd, wav_file = tempfile.mkstemp(prefix="ref_norm_", suffix=".wav", dir=str(tmp_dir))  # noqa: PTH123
            os.close(wav_fd)
            wav_path = Path(wav_file)
            sf.write(str(wav_path), audio, sample_rate)
            raw_path.unlink(missing_ok=True)
            return wav_path
        except EngineHTTPError:
            raw_path.unlink(missing_ok=True)
            raise
        except Exception as error:  # noqa: BLE001
            raw_path.unlink(missing_ok=True)
            raise EngineHTTPError(
                400,
                "INVALID_REFERENCE_AUDIO",
                f"No se pudo convertir el audio de referencia: {error}",
            ) from error

    def _default_reference_path(self, language: str) -> Path:
        prompt = DEFAULT_REFERENCE_PROMPTS.get(language)
        if prompt is None:
            raise EngineHTTPError(
                400,
                "DEFAULT_REFERENCE_UNAVAILABLE",
                f"No hay referencia por defecto empaquetada para el idioma '{language}'.",
            )

        target = self.prompts_dir / prompt["filename"]
        if target.exists() and target.stat().st_size > 0:
            return target

        part = target.with_suffix(f"{target.suffix}.part")
        self.log(f"Descargando referencia por defecto ({prompt['label']}) para idioma {language}...")
        try:
            with requests.get(prompt["url"], stream=True, timeout=30) as response:
                response.raise_for_status()
                with open(part, "wb") as stream:
                    for chunk in response.iter_content(chunk_size=1024 * 256):
                        if chunk:
                            stream.write(chunk)
        except Exception as error:  # noqa: BLE001
            part.unlink(missing_ok=True)
            raise EngineHTTPError(
                503,
                "DEFAULT_REFERENCE_DOWNLOAD_FAILED",
                f"No se pudo descargar la referencia por defecto para {language}: {error}",
            ) from error

        part.replace(target)
        return target

    @staticmethod
    def _segment_text(text: str, max_chars: int = MAX_SEGMENT_CHARS) -> list[str]:
        normalized = re.sub(r"\s+", " ", text).strip()
        if not normalized:
            return []
        if len(normalized) <= max_chars:
            return [normalized]

        sentences = [chunk.strip() for chunk in re.split(r"(?<=[.!?;:。！？])\s+", normalized) if chunk.strip()]
        segments: list[str] = []
        current = ""

        def flush_current() -> None:
            nonlocal current
            if current:
                segments.append(current)
                current = ""

        def push_long_sentence(sentence: str) -> None:
            words = [piece for piece in sentence.split(" ") if piece]
            chunk = ""
            for word in words:
                candidate = word if not chunk else f"{chunk} {word}"
                if len(candidate) <= max_chars:
                    chunk = candidate
                    continue
                if chunk:
                    segments.append(chunk)
                    chunk = ""
                while len(word) > max_chars:
                    segments.append(word[:max_chars])
                    word = word[max_chars:]
                chunk = word
            if chunk:
                segments.append(chunk)

        for sentence in sentences or [normalized]:
            if len(sentence) > max_chars:
                flush_current()
                push_long_sentence(sentence)
                continue

            candidate = sentence if not current else f"{current} {sentence}"
            if len(candidate) <= max_chars:
                current = candidate
            else:
                flush_current()
                current = sentence

        flush_current()
        return segments

    @staticmethod
    def _pcm_to_wav_bytes(pcm_bytes: bytes, sample_rate: int) -> bytes:
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(pcm_bytes)
        return buffer.getvalue()

    def _concatenate_wav_chunks(self, chunks: list[bytes], gap_ms: int = SEGMENT_GAP_MS) -> bytes:
        if not chunks:
            raise EngineHTTPError(500, "INFERENCE_FAILED", "No se genero ningun segmento de audio.")
        if len(chunks) == 1:
            return chunks[0]

        sample_rate: int | None = None
        pcm_chunks: list[bytes] = []
        for chunk in chunks:
            with wave.open(io.BytesIO(chunk), "rb") as wav:
                current_sr = int(wav.getframerate())
                if sample_rate is None:
                    sample_rate = current_sr
                elif current_sr != sample_rate:
                    raise EngineHTTPError(500, "INFERENCE_FAILED", "Los segmentos devueltos usan sample rates distintos.")
                pcm_chunks.append(wav.readframes(wav.getnframes()))

        assert sample_rate is not None
        silence = b"\0\0" * max(0, int(sample_rate * gap_ms / 1000))
        return self._pcm_to_wav_bytes(silence.join(pcm_chunks), sample_rate)

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
        return self.real_backend_cache_ready

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
        runtime_class = self._runtime_class()
        return {
            "platform": platform.platform(),
            "gpu_available": runtime_class == "real_gpu",
            "loaded_profile": self.loaded_profile,
            "profiles": list(MODEL_PROFILES.keys()),
            "simulate_download": self.simulate_download,
            "inference_backend": self.inference_backend,
            "backend_mode": self.backend_mode,
            "runtime_class": runtime_class,
            "quality_tier": self._quality_tier(),
            "real_backend_available": self.real_backend_available,
            "real_backend_device": self.real_backend_device,
            "real_backend_device_reason": self.real_backend_device_reason,
            "real_backend_cuda_index": self.real_backend_cuda_index,
            "real_backend_cuda_devices": self.real_backend_cuda_devices,
            "real_backend_torch_info": self.real_backend_torch_info,
            "real_backend_error": self.real_backend_error,
            "allowed_origins": self.allowed_origins,
            "allowed_origin_regex": self.allowed_origin_regex,
        }

    @staticmethod
    def _normalize_request_id(request_id: str | None) -> str:
        if request_id:
            cleaned = request_id.strip()
            if cleaned:
                return cleaned[:128]
        return f"req_{int(time.time() * 1000)}_{secrets.token_hex(4)}"

    @staticmethod
    def _validate_float_param(
        value: float | None,
        *,
        name: str,
        minimum: float,
        maximum: float,
        default: float,
    ) -> float:
        if value is None:
            return default
        numeric = float(value)
        if math.isnan(numeric) or math.isinf(numeric):
            raise EngineHTTPError(400, "INVALID_GENERATION_PARAM", f"Parametro invalido: {name}.")
        if numeric < minimum or numeric > maximum:
            raise EngineHTTPError(
                400,
                "INVALID_GENERATION_PARAM",
                f"{name} fuera de rango [{minimum}, {maximum}] (recibido: {numeric}).",
            )
        return numeric

    @staticmethod
    def _validate_seed(seed: int | None) -> int | None:
        if seed is None:
            return None
        numeric = int(seed)
        if numeric < MIN_SEED or numeric > MAX_SEED:
            raise EngineHTTPError(
                400,
                "INVALID_GENERATION_PARAM",
                f"seed fuera de rango [{MIN_SEED}, {MAX_SEED}] (recibido: {numeric}).",
            )
        return numeric

    def _resolve_generation_options(
        self,
        *,
        cfg_weight: float | None = None,
        exaggeration: float | None = None,
        temperature: float | None = None,
        seed: int | None = None,
    ) -> dict[str, Any]:
        return {
            "cfg_weight": self._validate_float_param(
                cfg_weight,
                name="cfg_weight",
                minimum=MIN_CFG_WEIGHT,
                maximum=MAX_CFG_WEIGHT,
                default=DEFAULT_CFG_WEIGHT,
            ),
            "exaggeration": self._validate_float_param(
                exaggeration,
                name="exaggeration",
                minimum=MIN_EXAGGERATION,
                maximum=MAX_EXAGGERATION,
                default=DEFAULT_EXAGGERATION,
            ),
            "temperature": self._validate_float_param(
                temperature,
                name="temperature",
                minimum=MIN_TEMPERATURE,
                maximum=MAX_TEMPERATURE,
                default=DEFAULT_TEMPERATURE,
            ),
            "seed": self._validate_seed(seed),
        }

    @staticmethod
    def _format_generation_options(options: dict[str, Any]) -> str:
        seed_label = options.get("seed")
        return (
            f"cfg_weight={options['cfg_weight']:.2f}, "
            f"exaggeration={options['exaggeration']:.2f}, "
            f"temperature={options['temperature']:.2f}, "
            f"seed={seed_label if seed_label is not None else 'auto'}"
        )

    @contextlib.contextmanager
    def _torch_seed_context(self, seed: int | None):
        if seed is None or self._torch is None:
            yield
            return

        torch_mod = self._torch
        devices: list[int] = []
        use_cuda_rng = str(self.real_backend_device).startswith("cuda")
        if use_cuda_rng:
            with contextlib.suppress(Exception):
                if torch_mod.cuda.is_available():
                    devices = list(range(int(torch_mod.cuda.device_count())))

        try:
            with torch_mod.random.fork_rng(devices=devices, enabled=True):
                torch_mod.manual_seed(seed)
                if devices:
                    torch_mod.cuda.manual_seed_all(seed)
                yield
                return
        except Exception:
            # Fallback path for torch builds without fork_rng support in this runtime.
            torch_mod.manual_seed(seed)
            if devices:
                torch_mod.cuda.manual_seed_all(seed)
            yield

    def _emit_event(
        self,
        request_id: str,
        phase: str,
        message: str,
        progress: float | None = None,
        level: str = "info",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": 0,
            "timestamp": time.time(),
            "request_id": request_id,
            "phase": phase,
            "level": level,
            "message": message,
        }
        if progress is not None:
            payload["progress"] = round(max(0.0, min(100.0, progress)), 2)

        with self.events_lock:
            self.events_cursor += 1
            payload["id"] = self.events_cursor
            self.events.append(payload)
            if len(self.events) > EVENT_BUFFER_LIMIT:
                del self.events[: len(self.events) - EVENT_BUFFER_LIMIT]

        self.log(f"[{request_id}] {phase}: {message}")
        return payload

    def _emit_sampling_progress(self, request_id: str, progress: float) -> None:
        clamped = round(max(0.0, min(100.0, progress)), 2)
        with self.events_lock:
            last = self.last_sampling_progress.get(request_id)
            should_emit = last is None or (clamped - last) >= SAMPLING_LOG_STEP_PERCENT or clamped >= 100.0
            if should_emit:
                self.last_sampling_progress[request_id] = clamped
        if should_emit:
            self._emit_event(
                request_id=request_id,
                phase="sampling",
                message=f"Sampling {clamped:.1f}%",
                progress=clamped,
            )

    def _clear_sampling_progress(self, request_id: str) -> None:
        with self.events_lock:
            self.last_sampling_progress.pop(request_id, None)

    def poll_events(self, cursor: int = 0, request_id: str | None = None, limit: int = 200) -> dict[str, Any]:
        cursor = max(0, int(cursor))
        limit = max(1, min(EVENT_POLL_MAX_LIMIT, int(limit)))

        with self.events_lock:
            filtered = [event for event in self.events if event["id"] > cursor]
            if request_id:
                filtered = [event for event in filtered if event["request_id"] == request_id]
            chunk = filtered[:limit]

        next_cursor = chunk[-1]["id"] if chunk else cursor
        return {
            "events": chunk,
            "next_cursor": next_cursor,
        }

    def get_download_status(self, profile: str) -> dict[str, Any]:
        profile = self._validate_profile(profile)
        with self._lock:
            job = self.download_jobs.get(profile)
            if job:
                return job.to_payload()

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

    def start_download(self, profile: str) -> dict[str, Any]:
        profile = self._validate_profile(profile)
        if self.real_backend_cache_ready:
            payload = self.get_download_status(profile)
            self.log(f"Perfil {profile} ya esta descargado.")
            return payload

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

        self.log(f"Descarga iniciada para perfil {profile} (cache de backend PyTorch).")
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

        with self._lock:
            if profile in self.loading_profiles:
                raise EngineHTTPError(409, "MODEL_LOADING", "El modelo ya se esta cargando.")
            self.loading_profiles.add(profile)

        try:
            self.log(f"Cargando perfil {profile} en memoria...")
            if self.inference_backend == "mock" and self.backend_mode == "mock":
                time.sleep(0.5)
            else:
                try:
                    self._ensure_real_backend_model()
                    self.real_backend_cache_ready = True
                except EngineHTTPError as error:
                    if not self._fallback_to_mock_runtime(error):
                        raise

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

    @contextlib.contextmanager
    def _sampling_hook_context(self, request_id: str):
        # chatterbox T3 uses tqdm(range(...), desc="Sampling"), we wrap it to forward progress.
        try:
            from chatterbox.models.t3 import t3 as t3_module
        except Exception:  # noqa: BLE001
            yield
            return

        original_tqdm = getattr(t3_module, "tqdm", None)
        if original_tqdm is None:
            yield
            return

        runtime = self

        def _iter_with_progress(iterable: Any, total: int) -> Any:
            total_safe = max(1, total)
            for index, item in enumerate(iterable, start=1):
                progress = 5.0 + (index / total_safe) * 90.0
                runtime._emit_sampling_progress(request_id, progress)
                yield item

        def _wrapped_tqdm(iterable: Any, *args: Any, **kwargs: Any) -> Any:
            desc = str(kwargs.get("desc", "")).strip().lower()
            total = kwargs.get("total")
            if total is None:
                with contextlib.suppress(TypeError):
                    total = len(iterable)  # type: ignore[arg-type]

            if total and "sampling" in desc:
                return _iter_with_progress(iterable, int(total))

            return original_tqdm(iterable, *args, **kwargs)

        t3_module.tqdm = _wrapped_tqdm
        try:
            yield
        finally:
            t3_module.tqdm = original_tqdm

    @staticmethod
    def _effective_cfg_weight(
        cfg_weight: float,
        *,
        target_language: str,
        reference_language: str | None,
    ) -> tuple[float, str | None]:
        if reference_language and reference_language != target_language and cfg_weight != 0.0:
            return 0.0, (
                "Referencia y salida parecen estar en idiomas distintos. "
                "Se fuerza cfg_weight=0.0 para reducir accent bleed."
            )
        return cfg_weight, None

    def _generate_real_audio(
        self,
        *,
        request_id: str,
        text: str,
        language: str,
        options: dict[str, Any],
        audio_prompt_path: Path | None = None,
        reference_language: str | None = None,
    ) -> bytes:
        assert self._real_model is not None

        sample_rate = int(getattr(self._real_model, "sr", 24000))
        segments = self._segment_text(text)
        if not segments:
            raise EngineHTTPError(400, "EMPTY_TEXT", "No hay texto utilizable para sintetizar.")

        if len(segments) > 1:
            self._emit_event(
                request_id,
                "segmenting_text",
                f"Texto largo detectado: {len(segments)} segmentos de hasta {MAX_SEGMENT_CHARS} caracteres.",
                progress=4.5,
            )

        adjusted_cfg_weight, cfg_note = self._effective_cfg_weight(
            float(options["cfg_weight"]),
            target_language=language,
            reference_language=reference_language,
        )
        if cfg_note:
            self._emit_event(request_id, "segmenting_text", cfg_note, progress=4.8)

        generated_chunks: list[bytes] = []
        with self._torch_seed_context(options["seed"]):
            for index, segment in enumerate(segments, start=1):
                segment_progress = 5.0 + ((index - 1) / max(1, len(segments))) * 80.0
                self._emit_event(
                    request_id,
                    "sampling",
                    f"Generando segmento {index}/{len(segments)}...",
                    progress=segment_progress,
                )
                generate_kwargs: dict[str, Any] = {
                    "language_id": language,
                    "exaggeration": options["exaggeration"],
                    "cfg_weight": adjusted_cfg_weight,
                    "temperature": options["temperature"],
                }
                if audio_prompt_path is not None:
                    generate_kwargs["audio_prompt_path"] = str(audio_prompt_path)
                with self._sampling_hook_context(request_id):
                    wav = self._real_model.generate(segment, **generate_kwargs)
                generated_chunks.append(self._wave_from_array(wav, sample_rate))
                self._clear_sampling_progress(request_id)

        return self._concatenate_wav_chunks(generated_chunks)

    def tts(
        self,
        text: str,
        profile: str,
        _language: str,
        request_id: str | None = None,
        use_default_reference: bool = True,
        cfg_weight: float | None = None,
        exaggeration: float | None = None,
        temperature: float | None = None,
        seed: int | None = None,
    ) -> bytes:
        profile = self._validate_profile(profile)
        req_id = self._normalize_request_id(request_id)
        options = self._resolve_generation_options(
            cfg_weight=cfg_weight,
            exaggeration=exaggeration,
            temperature=temperature,
            seed=seed,
        )
        options_label = self._format_generation_options(options)
        if self.loaded_profile != profile:
            self._emit_event(req_id, "failed", "El perfil solicitado no esta cargado.", level="error")
            raise EngineHTTPError(409, "MODEL_NOT_LOADED", "El perfil solicitado no esta cargado.")
        self._emit_event(req_id, "start", f"TTS iniciado ({_language}) [{options_label}].", progress=1.0)

        if self.inference_backend == "chatterbox":
            self._emit_event(req_id, "initializing_backend", "Validando backend real...", progress=3.0)
            try:
                self._ensure_real_backend_model()
                self._emit_event(
                    req_id,
                    "initializing_backend",
                    (
                        "Backend real activo: "
                        f"{self.real_backend_device} "
                        f"(reason={self.real_backend_device_reason})."
                    ),
                    progress=4.0,
                )
            except EngineHTTPError as error:
                if self._fallback_to_mock_runtime(error):
                    self._emit_event(
                        req_id,
                        "initializing_backend",
                        "Recursos del sistema insuficientes para modo Pro real. Continuando en modo compatible.",
                        progress=4.0,
                    )
                else:
                    self._emit_event(req_id, "failed", f"Fallo de inferencia TTS: {error.message}", level="error", progress=100.0)
                    raise

        if self.inference_backend == "chatterbox":
            reference_path: Path | None = None
            try:
                if use_default_reference:
                    self._emit_event(req_id, "preparing_reference", "Resolviendo referencia por defecto del idioma...", progress=4.0)
                    reference_path = self._default_reference_path(_language)
                    self._emit_event(
                        req_id,
                        "preparing_reference",
                        f"Referencia por defecto lista: {reference_path.name}.",
                        progress=4.2,
                    )

                wav_bytes = self._generate_real_audio(
                    request_id=req_id,
                    text=text,
                    language=_language,
                    options=options,
                    audio_prompt_path=reference_path,
                    reference_language=_language if use_default_reference else None,
                )
                self._emit_event(req_id, "serializing_audio", "Serializando WAV...", progress=96.0)
                self._emit_event(req_id, "completed", "TTS completado.", progress=100.0)
                return wav_bytes
            except EngineHTTPError:
                self._emit_event(req_id, "failed", "Fallo de inferencia TTS.", level="error", progress=100.0)
                raise
            except Exception as error:  # noqa: BLE001
                self._emit_event(req_id, "failed", f"Fallo de inferencia TTS: {error}", level="error", progress=100.0)
                raise EngineHTTPError(500, "INFERENCE_FAILED", str(error)) from error
            finally:
                self._clear_sampling_progress(req_id)

        segments = self._segment_text(text)
        self._emit_event(req_id, "sampling", f"Generando audio sintetico (mock) [{options_label}]...", progress=50.0)
        wav_bytes = self._concatenate_wav_chunks(
            [self._synthesize_wave(text=segment, sample_rate=24000, voice_bias_hz=0.0) for segment in segments]
        )
        self._emit_event(req_id, "completed", "TTS mock completado.", progress=100.0)
        return wav_bytes

    def clone(
        self,
        text: str,
        profile: str,
        _language: str,
        reference_audio: bytes,
        reference_extension: str,
        request_id: str | None = None,
        cfg_weight: float | None = None,
        exaggeration: float | None = None,
        temperature: float | None = None,
        seed: int | None = None,
    ) -> bytes:
        profile = self._validate_profile(profile)
        req_id = self._normalize_request_id(request_id)
        options = self._resolve_generation_options(
            cfg_weight=cfg_weight,
            exaggeration=exaggeration,
            temperature=temperature,
            seed=seed,
        )
        options_label = self._format_generation_options(options)
        if self.loaded_profile != profile:
            self._emit_event(req_id, "failed", "El perfil solicitado no esta cargado.", level="error")
            raise EngineHTTPError(409, "MODEL_NOT_LOADED", "El perfil solicitado no esta cargado.")
        if len(reference_audio) < 1024:
            self._emit_event(req_id, "failed", "El audio de referencia es demasiado corto.", level="error")
            raise EngineHTTPError(400, "INVALID_REFERENCE_AUDIO", "El audio de referencia es demasiado corto.")
        self._emit_event(req_id, "start", f"Clone iniciado ({_language}) [{options_label}].", progress=1.0)
        if self.inference_backend == "chatterbox":
            self._emit_event(req_id, "initializing_backend", "Validando backend real...", progress=3.0)
            try:
                self._ensure_real_backend_model()
                self._emit_event(
                    req_id,
                    "initializing_backend",
                    (
                        "Backend real activo: "
                        f"{self.real_backend_device} "
                        f"(reason={self.real_backend_device_reason})."
                    ),
                    progress=4.0,
                )
            except EngineHTTPError as error:
                if self._fallback_to_mock_runtime(error):
                    self._emit_event(
                        req_id,
                        "initializing_backend",
                        "Recursos del sistema insuficientes para clonacion real. Continuando en modo compatible.",
                        progress=4.0,
                    )
                else:
                    self._emit_event(
                        req_id,
                        "failed",
                        f"Fallo de inferencia de clonacion: {error.message}",
                        level="error",
                        progress=100.0,
                    )
                    raise
        if self.inference_backend == "chatterbox":
            self._emit_event(req_id, "preparing_reference", "Preparando audio de referencia...", progress=4.0)
            reference_path = self._prepare_reference_audio_path(reference_audio, reference_extension)
            try:
                wav_bytes = self._generate_real_audio(
                    request_id=req_id,
                    text=text,
                    language=_language,
                    options=options,
                    audio_prompt_path=reference_path,
                )
                self._emit_event(req_id, "serializing_audio", "Serializando WAV...", progress=96.0)
                self._emit_event(req_id, "completed", "Clone completado.", progress=100.0)
                return wav_bytes
            except EngineHTTPError:
                self._emit_event(req_id, "failed", "Fallo de inferencia de clonacion.", level="error", progress=100.0)
                raise
            except Exception as error:  # noqa: BLE001
                self._emit_event(req_id, "failed", f"Fallo de inferencia de clonacion: {error}", level="error", progress=100.0)
                raise EngineHTTPError(500, "INFERENCE_FAILED", str(error)) from error
            finally:
                self._clear_sampling_progress(req_id)
                reference_path.unlink(missing_ok=True)
        bias = self._voice_bias(reference_audio)
        self._emit_event(req_id, "sampling", f"Generando clon sintetico (mock) [{options_label}]...", progress=50.0)
        wav_bytes = self._concatenate_wav_chunks(
            [self._synthesize_wave(text=segment, sample_rate=24000, voice_bias_hz=bias) for segment in self._segment_text(text)]
        )
        self._emit_event(req_id, "completed", "Clone mock completado.", progress=100.0)
        return wav_bytes


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

    @app.get("/events/poll")
    async def events_poll(
        request: Request,
        cursor: int = 0,
        request_id: str | None = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        runtime.authorize(request)
        return runtime.poll_events(cursor=cursor, request_id=request_id, limit=limit)

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
        req_id = runtime._normalize_request_id(body.request_id)
        started_at = time.perf_counter()
        wav_bytes = runtime.tts(
            body.text,
            body.quality_profile,
            body.language,
            request_id=req_id,
            use_default_reference=body.use_default_reference,
            cfg_weight=body.cfg_weight,
            exaggeration=body.exaggeration,
            temperature=body.temperature,
            seed=body.seed,
        )
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        headers = {
            "X-Engine-Mode": "pro-local",
            "X-Model-Profile": body.quality_profile,
            "X-Latency-Ms": str(elapsed_ms),
            "X-Request-Id": req_id,
        }
        return StreamingResponse(io.BytesIO(wav_bytes), media_type="audio/wav", headers=headers)

    @app.post("/clone")
    async def clone(
        request: Request,
        text: str = Form(...),
        language: str = Form("es"),
        quality_profile: str = Form(PRO_PROFILE),
        request_id: str | None = Form(None),
        cfg_weight: float | None = Form(None),
        exaggeration: float | None = Form(None),
        temperature: float | None = Form(None),
        seed: int | None = Form(None),
        reference_audio: UploadFile = File(...),
    ) -> StreamingResponse:
        runtime.authorize(request)
        req_id = runtime._normalize_request_id(request_id)
        filename = reference_audio.filename or ""
        extension = Path(filename).suffix.lower()
        if extension not in {".wav", ".mp3", ".mpeg", ".x-wav"}:
            raise EngineHTTPError(400, "INVALID_REFERENCE_AUDIO", "Formato no soportado. Usa WAV o MP3.")

        payload = await _read_upload_bytes_limited(reference_audio, max_bytes=MAX_REFERENCE_AUDIO_BYTES)
        started_at = time.perf_counter()
        wav_bytes = runtime.clone(
            text,
            quality_profile,
            language,
            payload,
            extension,
            request_id=req_id,
            cfg_weight=cfg_weight,
            exaggeration=exaggeration,
            temperature=temperature,
            seed=seed,
        )
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        headers = {
            "X-Engine-Mode": "pro-local",
            "X-Model-Profile": quality_profile,
            "X-Latency-Ms": str(elapsed_ms),
            "X-Request-Id": req_id,
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
