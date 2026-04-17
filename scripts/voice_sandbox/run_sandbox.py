"""CLI entry point.

실행:
    python -m scripts.voice_sandbox.run_sandbox
    python -m scripts.voice_sandbox.run_sandbox --list-devices
    python -m scripts.voice_sandbox.run_sandbox --config path/to/other.yaml
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from .asr_whisper import ASRConfig
from .audio_source import AudioConfig, apply_mic_gain, list_devices
from .pipeline import Pipeline
from .recorder import UtteranceRecorder
from .vad_silero import VADConfig
from .wake_word import WakeConfig


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = Path(__file__).resolve().parent / "config.yaml"


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="RIO voice recognition sandbox")
    p.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Path to YAML config")
    p.add_argument("--list-devices", action="store_true", help="List audio devices and exit")
    return p.parse_args()


def _load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _build_configs(cfg: dict) -> tuple[AudioConfig, VADConfig, ASRConfig, WakeConfig]:
    audio_cfg = AudioConfig(
        device=cfg["audio"].get("device"),
        sample_rate=cfg["audio"]["sample_rate"],
        channels=cfg["audio"]["channels"],
        blocksize=cfg["audio"]["blocksize"],
        dtype=cfg["audio"]["dtype"],
    )
    vad_cfg = VADConfig(
        threshold=cfg["vad"]["threshold"],
        min_silence_duration_ms=cfg["vad"]["min_silence_duration_ms"],
        speech_pad_ms=cfg["vad"]["speech_pad_ms"],
        min_speech_ms=cfg["vad"]["min_speech_ms"],
        sample_rate=cfg["audio"]["sample_rate"],
    )
    asr_cfg = ASRConfig(
        model=cfg["asr"]["model"],
        language=cfg["asr"]["language"],
        beam_size=cfg["asr"]["beam_size"],
        compute_type=cfg["asr"]["compute_type"],
        device=cfg["asr"]["device"],
        no_speech_threshold=cfg["asr"]["no_speech_threshold"],
        condition_on_previous_text=cfg["asr"]["condition_on_previous_text"],
    )
    wake_cfg = WakeConfig(
        phrase=cfg["wake_word"]["phrase"],
        aliases=list(cfg["wake_word"]["aliases"]),
        fuzzy=cfg["wake_word"]["fuzzy"],
        max_edit_distance=cfg["wake_word"]["max_edit_distance"],
        cooldown_ms=cfg["wake_word"]["cooldown_ms"],
        listen_window_ms=cfg["wake_word"]["listen_window_ms"],
        extend_on_command=cfg["wake_word"]["extend_on_command"],
        min_asr_logprob=cfg["wake_word"]["min_asr_logprob"],
        strip_from_command=cfg["wake_word"]["strip_from_command"],
    )
    return audio_cfg, vad_cfg, asr_cfg, wake_cfg


def main() -> int:
    args = _parse_args()

    if args.list_devices:
        print(list_devices())
        return 0

    if not args.config.exists():
        print(f"[run] config not found: {args.config}", file=sys.stderr)
        return 1

    cfg = _load_yaml(args.config)
    audio_cfg, vad_cfg, asr_cfg, wake_cfg = _build_configs(cfg)

    mic_gain = cfg["audio"].get("mic_gain_percent")
    if mic_gain is not None:
        apply_mic_gain(int(mic_gain), cfg["audio"].get("gain_target_source"))

    save_dir_rel = cfg["logging"]["save_dir"]
    save_dir = Path(save_dir_rel)
    if not save_dir.is_absolute():
        save_dir = REPO_ROOT / save_dir_rel

    recorder = UtteranceRecorder(
        save_dir=save_dir,
        sample_rate=audio_cfg.sample_rate,
        enabled=bool(cfg["logging"]["save_utterances"]),
    )

    pipeline = Pipeline(audio_cfg, vad_cfg, asr_cfg, wake_cfg, recorder)
    pipeline.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
