"""Lottie JSON 을 가로 스프라이트 시트 PNG 로 변환.

런타임에 rlottie 의존을 두지 않기 위해 빌드 타임에 한 번만 실행한다.
렌더된 RGBA 프레임들을 정해진 개수만큼 균등 간격으로 샘플링해서
가로로 이어붙인 단일 PNG 를 assets/animations 에 만든다.

사용 예:
    python scripts/tools/lottie_to_sprite.py \
        --input assets/animations/listening.json \
        --output assets/animations/listening_sprite.png \
        --size 200 --frames 24
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image
from rlottie_python import LottieAnimation


def render_sprite_sheet(
    lottie_path: Path,
    output_path: Path,
    cell_size: int,
    frame_count: int,
) -> None:
    anim = LottieAnimation.from_file(str(lottie_path))
    total_frames = anim.lottie_animation_get_totalframe()
    sample_indices = np.linspace(0, total_frames - 1, frame_count, dtype=int)

    sheet = Image.new("RGBA", (cell_size * frame_count, cell_size), (0, 0, 0, 0))

    for column, frame_idx in enumerate(sample_indices):
        buf = anim.lottie_animation_render(
            frame_num=int(frame_idx),
            width=cell_size,
            height=cell_size,
        )
        frame_rgba = np.frombuffer(buf, dtype=np.uint8).reshape(cell_size, cell_size, 4)
        # rlottie 는 BGRA 로 반환하므로 RGB 채널 순서 교환.
        frame_rgba = frame_rgba[..., [2, 1, 0, 3]]
        sheet.paste(Image.fromarray(frame_rgba, mode="RGBA"), (column * cell_size, 0))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path, format="PNG", optimize=True)
    print(
        f"wrote {output_path} "
        f"({frame_count} frames x {cell_size}px, source total_frames={total_frames})"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Lottie JSON path")
    parser.add_argument("--output", type=Path, required=True, help="Sprite sheet PNG path")
    parser.add_argument("--size", type=int, default=200, help="Per-frame pixel size (square)")
    parser.add_argument("--frames", type=int, default=24, help="Number of sampled frames")
    args = parser.parse_args()
    render_sprite_sheet(args.input, args.output, args.size, args.frames)


if __name__ == "__main__":
    main()
