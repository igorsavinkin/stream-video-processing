from __future__ import annotations

import argparse
import time
from pathlib import Path

import cv2

from src.config import load_settings
from src.ingest.rtsp_reader import RTSPFrameReader


def capture_frames(output_dir: Path, max_frames: int) -> None:
    settings = load_settings()
    output_dir.mkdir(parents=True, exist_ok=True)
    reader = RTSPFrameReader(
        settings.rtsp_url,
        target_fps=settings.frame_sample_fps,
        width=settings.frame_width,
        height=settings.frame_height,
    ).start()

    saved = 0
    try:
        while saved < max_frames:
            frame = reader.read()
            if frame is None:
                time.sleep(0.1)
                continue
            filename = output_dir / f"frame_{int(time.time() * 1000)}.jpg"
            cv2.imwrite(str(filename), frame)
            saved += 1
    finally:
        reader.stop()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("data/raw"))
    parser.add_argument("--max-frames", type=int, default=50)
    args = parser.parse_args()
    capture_frames(args.output, args.max_frames)


if __name__ == "__main__":
    main()
