"""Voice sandbox CLI.

실행 예:
    python scripts/voice_sandbox/run_sandbox.py
    python scripts/voice_sandbox/run_sandbox.py --mode transcript
    python -m scripts.voice_sandbox.run_sandbox --list-devices
    python -m scripts.voice_sandbox.run_sandbox --config configs/voice_sandbox.yaml
"""
from __future__ import annotations

import argparse
import copy
import sys
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.voice_sandbox.asr_whisper import ASRConfig
from scripts.voice_sandbox.audio_source import (
    AudioConfig,
    apply_mic_gain,
    ensure_default_input_source,
    list_devices,
)
from scripts.voice_sandbox.pipeline import Pipeline
from scripts.voice_sandbox.recorder import UtteranceRecorder
from scripts.voice_sandbox.rust_frontend import RustFrontendConfig
from scripts.voice_sandbox.vad_rms import VADConfig
from scripts.voice_sandbox.wake_word import WakeConfig


DEFAULT_CONFIG = REPO_ROOT / "configs" / "voice_sandbox.yaml"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RIO voice recognition sandbox")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Path to YAML config")
    parser.add_argument("--list-devices", action="store_true", help="List audio devices and exit")
    parser.add_argument(
        "--mode",
        choices=("transcript", "intent", "wake"),
        default=None,
        help="Override pipeline mode from config",
    )
    parser.add_argument(
        "--backend",
        choices=("python", "rust"),
        default=None,
        help="Override backend.type from config for sandbox audio frontend",
    )
    return parser.parse_args()


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _resolve_config(path: Path) -> dict[str, Any]:
    target = path if path.is_absolute() else REPO_ROOT / path
    cfg = _load_yaml(target)
    extends = cfg.get("extends")
    if not extends:
        return cfg

    base_path = Path(str(extends))
    if not base_path.is_absolute():
        candidate = (target.parent / base_path).resolve()
        base_path = candidate if candidate.exists() else REPO_ROOT / base_path
    base_cfg = _resolve_config(base_path)

    child_cfg = dict(cfg)
    child_cfg.pop("extends", None)
    return _deep_merge(base_cfg, child_cfg)


def _build_configs(cfg: dict[str, Any]) -> tuple[AudioConfig, VADConfig, ASRConfig, WakeConfig]:
    audio = dict(cfg.get("audio") or {})
    vad = dict(cfg.get("vad") or {})
    asr = dict(cfg.get("asr") or {})
    wake = dict(cfg.get("wake_word") or {})

    audio_cfg = AudioConfig(
        device=audio.get("device"),
        sample_rate=int(audio.get("sample_rate", 16000)),
        channels=int(audio.get("channels", 1)),
        blocksize=int(audio.get("blocksize", 512)),
        dtype=str(audio.get("dtype", "float32")),
    )
    threshold_value = vad.get("threshold", 350)
    threshold = int(round(float(threshold_value)))
    if isinstance(threshold_value, (float, int)) and 0.0 <= float(threshold_value) <= 1.0:
        threshold = 350
    vad_cfg = VADConfig(
        threshold=threshold,
        min_silence_duration_ms=int(vad.get("min_silence_duration_ms", 300)),
        speech_pad_ms=int(vad.get("speech_pad_ms", 30)),
        min_speech_ms=int(vad.get("min_speech_ms", 150)),
        sample_rate=audio_cfg.sample_rate,
    )
    asr_cfg = ASRConfig(
        model=str(asr.get("model", "base")),
        language=str(asr.get("language", "ko")),
        beam_size=int(asr.get("beam_size", 1)),
        compute_type=str(asr.get("compute_type", "int8")),
        device=str(asr.get("device", "cpu")),
        no_speech_threshold=float(asr.get("no_speech_threshold", 0.6)),
        condition_on_previous_text=bool(asr.get("condition_on_previous_text", True)),
    )
    wake_cfg = WakeConfig(
        phrase=str(wake.get("phrase", "리오야")),
        aliases=[str(item) for item in list(wake.get("aliases") or ["리오야", "리오", "rio"])],
        fuzzy=bool(wake.get("fuzzy", True)),
        max_edit_distance=int(wake.get("max_edit_distance", 1)),
        cooldown_ms=int(wake.get("cooldown_ms", 1500)),
        listen_window_ms=int(wake.get("listen_window_ms", 3000)),
        extend_on_command=bool(wake.get("extend_on_command", True)),
        min_asr_logprob=float(wake.get("min_asr_logprob", -1.0)),
        strip_from_command=bool(wake.get("strip_from_command", True)),
    )
    return audio_cfg, vad_cfg, asr_cfg, wake_cfg


def main() -> int:
    args = _parse_args()

    if args.list_devices:
        print(list_devices())
        return 0

    config_path = args.config if args.config.is_absolute() else REPO_ROOT / args.config
    if not config_path.exists():
        print(f"[run] config not found: {config_path}", file=sys.stderr)
        return 1

    cfg = _resolve_config(config_path)
    audio_cfg, vad_cfg, asr_cfg, wake_cfg = _build_configs(cfg)

    mode = args.mode or str(cfg.get("mode") or "intent")
    if mode not in {"transcript", "intent", "wake"}:
        print(f"[run] unsupported mode: {mode}", file=sys.stderr)
        return 1

    backend_cfg = dict(cfg.get("backend") or {})
    backend_type = str(args.backend or backend_cfg.get("type") or "python").strip().lower()
    if backend_type not in {"python", "rust"}:
        print(f"[run] unsupported backend: {backend_type}", file=sys.stderr)
        return 1

    if audio_cfg.device in {"pulse", "default"}:
        gain_source = cfg.get("audio", {}).get("gain_target_source") if isinstance(cfg.get("audio"), dict) else None
        ensure_default_input_source(gain_source)

    mic_gain = cfg.get("audio", {}).get("mic_gain_percent") if isinstance(cfg.get("audio"), dict) else None
    if mic_gain is not None:
        gain_source = cfg.get("audio", {}).get("gain_target_source") if isinstance(cfg.get("audio"), dict) else None
        apply_mic_gain(int(mic_gain), gain_source)

    logging_cfg = dict(cfg.get("logging") or {})
    save_dir_value = str(logging_cfg.get("save_dir") or "artifacts/voice_sandbox")
    save_dir = Path(save_dir_value)
    if not save_dir.is_absolute():
        save_dir = REPO_ROOT / save_dir

    recorder = UtteranceRecorder(
        save_dir=save_dir,
        sample_rate=audio_cfg.sample_rate,
        enabled=bool(logging_cfg.get("save_utterances", True)),
    )

    pipeline = Pipeline(
        audio_cfg,
        vad_cfg,
        asr_cfg,
        recorder,
        mode=mode,
        wake_cfg=wake_cfg if mode == "wake" else None,
        backend_type=backend_type,
        rust_frontend_cfg=(
            RustFrontendConfig(
                worker_path=str(
                    backend_cfg.get(
                        "worker_path",
                        "native/bin/rio-audio-worker",
                    )
                ),
                config_path=config_path,
                startup_timeout_ms=int(backend_cfg.get("startup_timeout_ms", 3000)),
            )
            if backend_type == "rust"
            else None
        ),
    )
    pipeline.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
