#!/usr/bin/env python3
"""Standalone camera preview + face-detection debug utility.

Runs independently from ``app.main`` — open a second terminal and launch
this script to see what the vision worker would see. Useful for:

- Confirming the webcam is wired to the expected ``/dev/video*`` index.
- Visual tuning of ``face_confidence_min`` in ``configs/thresholds.yaml``.
- Sanity-checking MediaPipe installation before spinning up RIO.

Run::

    python3 scripts/preview_camera.py                 # defaults
    python3 scripts/preview_camera.py --device 1      # second webcam
    python3 scripts/preview_camera.py --min-conf 0.5

Controls:
    q       quit
    space   toggle detection overlay
    s       save a snapshot to ``scripts/_preview_snap_<n>.jpg``
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


def _fail(msg: str, exit_code: int = 1) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(exit_code)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RIO camera preview")
    parser.add_argument("--device", type=int, default=0, help="V4L2 device index")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--min-conf", type=float, default=0.6,
                        help="MediaPipe face_confidence_min")
    parser.add_argument("--model", type=int, default=0, choices=[0, 1],
                        help="MediaPipe model_selection (0=<2m, 1=full-range)")
    args = parser.parse_args(argv)

    try:
        import cv2  # type: ignore
    except ImportError:
        _fail("opencv-python is required: pip install opencv-python")

    try:
        import mediapipe as mp  # type: ignore
    except ImportError:
        _fail("mediapipe is required: pip install mediapipe")

    cap = cv2.VideoCapture(args.device)
    if not cap.isOpened():
        _fail(f"cannot open /dev/video{args.device}")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)

    face = mp.solutions.face_detection.FaceDetection(
        model_selection=args.model,
        min_detection_confidence=args.min_conf,
    )

    window = "RIO camera preview"
    cv2.namedWindow(window, cv2.WINDOW_NORMAL)
    show_overlay = True
    snap_idx = 0
    fps = 0.0
    last_t = time.monotonic()

    try:
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                print("WARN: frame grab failed", file=sys.stderr)
                continue

            h, w = frame.shape[:2]
            detections_out: list[tuple[int, int, int, int, float, float, float]] = []

            if show_overlay:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = face.process(rgb)
                if result.detections:
                    for det in result.detections:
                        rel = det.location_data.relative_bounding_box
                        x = int(max(0.0, rel.xmin) * w)
                        y = int(max(0.0, rel.ymin) * h)
                        bw = int(rel.width * w)
                        bh = int(rel.height * h)
                        cx_n = rel.xmin + rel.width / 2.0
                        cy_n = rel.ymin + rel.height / 2.0
                        conf = float(det.score[0]) if det.score else 0.0
                        detections_out.append((x, y, bw, bh, cx_n, cy_n, conf))

            # Draw bboxes + labels.
            for (x, y, bw, bh, cx_n, cy_n, conf) in detections_out:
                cv2.rectangle(frame, (x, y), (x + bw, y + bh), (0, 255, 0), 2)
                cv2.circle(
                    frame,
                    (int(cx_n * w), int(cy_n * h)),
                    4, (0, 255, 255), -1,
                )
                label = f"c=({cx_n:.2f},{cy_n:.2f}) p={conf:.2f}"
                cv2.putText(
                    frame, label, (x, max(0, y - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1, cv2.LINE_AA,
                )

            # HUD: fps + detection count + controls hint.
            now = time.monotonic()
            dt = max(1e-3, now - last_t)
            fps = 0.9 * fps + 0.1 / dt if fps > 0 else 1.0 / dt
            last_t = now
            hud = (
                f"{fps:5.1f} fps  faces={len(detections_out)}  "
                f"overlay={'ON' if show_overlay else 'OFF'}  "
                f"(q:quit  space:toggle  s:snap)"
            )
            cv2.putText(
                frame, hud, (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2, cv2.LINE_AA,
            )

            cv2.imshow(window, frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                break
            elif key == ord(" "):
                show_overlay = not show_overlay
            elif key == ord("s"):
                out = Path(__file__).resolve().parent / f"_preview_snap_{snap_idx:03d}.jpg"
                cv2.imwrite(str(out), frame)
                snap_idx += 1
                print(f"saved {out}")
    finally:
        cap.release()
        cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
