"""pactl 기반 mic 게인 자동 설정.

PipeWire/PulseAudio 환경에서 특정 source 의 입력 볼륨을 지정 퍼센트로 설정.
pactl 이 없거나 실패해도 예외는 던지지 않고 경고 로그만 남김.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from typing import Optional


_LOGGER = logging.getLogger(__name__)


def _run_pactl(args: list[str]) -> tuple[int, str, str]:
    if shutil.which("pactl") is None:
        return -1, "", "pactl not found"
    try:
        r = subprocess.run(["pactl", *args], capture_output=True, text=True, timeout=3)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except subprocess.TimeoutExpired:
        return -2, "", "pactl timeout"


def _get_default_source() -> Optional[str]:
    code, out, _ = _run_pactl(["info"])
    if code != 0:
        return None
    for line in out.splitlines():
        if line.startswith("Default Source:"):
            return line.split(":", 1)[1].strip()
    return None


def _find_source_by_hint(hint: str) -> Optional[str]:
    """input source (`alsa_input.*`) 를 우선 매칭. 헤드셋처럼 output monitor 도
    같은 이름을 갖는 경우 monitor 가 먼저 잡히는 걸 방지."""
    code, out, _ = _run_pactl(["list", "short", "sources"])
    if code != 0:
        return None
    fallback: Optional[str] = None
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        name = parts[1]
        if hint not in name:
            continue
        if name.startswith("alsa_input."):
            return name
        if fallback is None:
            fallback = name
    return fallback


def apply_mic_gain(percent: int, source_hint: Optional[str] = None) -> None:
    """pactl 로 mic 게인을 percent % 로 설정. 실패해도 예외 없음."""
    source = _find_source_by_hint(source_hint) if source_hint else _get_default_source()
    if source is None:
        _LOGGER.warning("mic gain: source not found (hint=%r) — leaving volume unchanged", source_hint)
        return

    code, _out, err = _run_pactl(["set-source-volume", source, f"{percent}%"])
    if code != 0:
        _LOGGER.warning("mic gain set FAILED on '%s': %s", source, err)
        return

    _, vol_out, _ = _run_pactl(["get-source-volume", source])
    summary = vol_out.splitlines()[0] if vol_out else ""
    _LOGGER.info("mic gain → %d%% on '%s' | %s", percent, source, summary)
