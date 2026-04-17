"""Figma rosto PNG → RIO 에셋 변환 스크립트.

assets/figma_reference/rosto-XX.png (2560x1440) →
assets/expressions/<mood>.png (1024x600)

실행: py tools/prepare_assets.py
"""
import shutil
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("Pillow required: pip install Pillow")
    sys.exit(1)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "assets" / "figma_reference"
DST_DIR = PROJECT_ROOT / "assets" / "expressions"

TARGET_W, TARGET_H = 1024, 600

# ── Figma rosto → RIO mood 매핑 ─────────────────────────────
MAPPING = {
    # primary (state-machine 필수)
    "rosto-02": "calm",
    "rosto-22": "attentive",
    "rosto-10": "sleepy",
    "rosto-29": "alert",
    "rosto-03": "startled",
    "rosto-14": "confused",
    "rosto-04": "welcome",
    "rosto-24": "happy",
    # secondary (Executing kind / 특수 장면)
    "rosto-23": "photo_ready",
    "rosto-18": "photo_snap",
    "rosto-06": "game_face",
    "rosto-07": "dance_face",
    "rosto-16": "smarthome_fail",
    "rosto-25": "weather_face",
    "rosto-12": "petting",
    "rosto-11": "ko_defeated",
    "rosto-08": "boot",
}


def convert(src_path: Path, dst_path: Path) -> None:
    img = Image.open(src_path)
    img = img.resize((TARGET_W, TARGET_H), Image.LANCZOS)
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(dst_path, "PNG")


def main() -> None:
    if not SRC_DIR.exists():
        print(f"Source directory not found: {SRC_DIR}")
        sys.exit(1)

    DST_DIR.mkdir(parents=True, exist_ok=True)
    converted = 0
    skipped = 0

    for rosto_name, mood_name in MAPPING.items():
        src = SRC_DIR / f"{rosto_name}.png"
        dst = DST_DIR / f"{mood_name}.png"

        if not src.exists():
            print(f"  SKIP  {rosto_name}.png (file not found)")
            skipped += 1
            continue

        convert(src, dst)
        print(f"  OK    {rosto_name}.png → {mood_name}.png  ({TARGET_W}x{TARGET_H})")
        converted += 1

    print(f"\nDone: {converted} converted, {skipped} skipped")
    print(f"Output: {DST_DIR}")


if __name__ == "__main__":
    main()
