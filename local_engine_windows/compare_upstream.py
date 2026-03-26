from __future__ import annotations

import argparse
import json
from pathlib import Path

import requests

from local_engine_windows.daemon import EngineRuntime, PRO_PROFILE


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compara daemon local vs upstream Chatterbox.")
    parser.add_argument("--text", required=True, help="Texto a sintetizar.")
    parser.add_argument("--language", choices=["es", "en"], default="es")
    parser.add_argument("--reference", help="Ruta a audio de referencia opcional.")
    parser.add_argument("--engine-url", default="http://127.0.0.1:57641")
    parser.add_argument("--token", help="Token del daemon local. Si se omite, se usa el token persistente.")
    parser.add_argument("--output-dir", default="local_engine_windows/compare_output")
    parser.add_argument("--cfg-weight", type=float, default=0.5)
    parser.add_argument("--exaggeration", type=float, default=0.5)
    parser.add_argument("--temperature", type=float, default=0.8)
    parser.add_argument("--seed", type=int, default=0)
    return parser.parse_args()


def save_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def build_upstream_audio(runtime: EngineRuntime, args: argparse.Namespace) -> bytes:
    if runtime._chatterbox_class is None or runtime._torch is None:
        raise RuntimeError("Chatterbox no esta disponible en este entorno.")

    target_device = runtime.real_backend_device if runtime._runtime_class() == "real_gpu" else "cpu"
    model = runtime._chatterbox_class.from_pretrained(device=runtime._torch.device(target_device))

    reference_path: Path | None = None
    temp_reference_path: Path | None = None
    if args.reference:
        reference_bytes = Path(args.reference).read_bytes()
        temp_reference_path = runtime._prepare_reference_audio_path(reference_bytes, Path(args.reference).suffix)
        reference_path = temp_reference_path
    else:
        reference_path = runtime._default_reference_path(args.language)

    options = {
        "cfg_weight": args.cfg_weight,
        "exaggeration": args.exaggeration,
        "temperature": args.temperature,
        "seed": None if args.seed == 0 else args.seed,
    }

    chunks: list[bytes] = []
    try:
        with runtime._torch_seed_context(options["seed"]):
            for segment in runtime._segment_text(args.text):
                kwargs = {
                    "language_id": args.language,
                    "cfg_weight": options["cfg_weight"],
                    "exaggeration": options["exaggeration"],
                    "temperature": options["temperature"],
                    "audio_prompt_path": str(reference_path),
                }
                wav = model.generate(segment, **kwargs)
                chunks.append(runtime._wave_from_array(wav, int(getattr(model, "sr", 24000))))
        return runtime._concatenate_wav_chunks(chunks)
    finally:
        if temp_reference_path is not None:
            temp_reference_path.unlink(missing_ok=True)


def fetch_daemon_audio(runtime: EngineRuntime, args: argparse.Namespace) -> bytes:
    token = args.token or runtime.api_token
    headers = {"Authorization": f"Bearer {token}"}
    if args.reference:
        with Path(args.reference).open("rb") as stream:
            response = requests.post(
                f"{args.engine_url}/clone",
                headers=headers,
                data={
                    "text": args.text,
                    "language": args.language,
                    "quality_profile": PRO_PROFILE,
                    "cfg_weight": str(args.cfg_weight),
                    "exaggeration": str(args.exaggeration),
                    "temperature": str(args.temperature),
                    "seed": str(args.seed),
                },
                files={"reference_audio": (Path(args.reference).name, stream, "audio/wav")},
                timeout=300,
            )
    else:
        response = requests.post(
            f"{args.engine_url}/tts",
            headers={**headers, "Content-Type": "application/json"},
            data=json.dumps(
                {
                    "text": args.text,
                    "language": args.language,
                    "quality_profile": PRO_PROFILE,
                    "use_default_reference": True,
                    "cfg_weight": args.cfg_weight,
                    "exaggeration": args.exaggeration,
                    "temperature": args.temperature,
                    "seed": args.seed,
                }
            ),
            timeout=300,
        )
    response.raise_for_status()
    return response.content


def main() -> None:
    args = parse_args()
    runtime = EngineRuntime()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    daemon_bytes = fetch_daemon_audio(runtime, args)
    upstream_bytes = build_upstream_audio(runtime, args)

    daemon_path = output_dir / "daemon.wav"
    upstream_path = output_dir / "upstream.wav"
    save_bytes(daemon_path, daemon_bytes)
    save_bytes(upstream_path, upstream_bytes)

    print(f"daemon={daemon_path} ({len(daemon_bytes)} bytes)")
    print(f"upstream={upstream_path} ({len(upstream_bytes)} bytes)")


if __name__ == "__main__":
    main()
