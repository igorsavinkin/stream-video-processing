from __future__ import annotations

from pathlib import Path
from typing import Tuple

import cv2
import numpy as np
from PIL import Image


def resize_frame(frame: np.ndarray, size: Tuple[int, int]) -> np.ndarray:
    return cv2.resize(frame, size, interpolation=cv2.INTER_AREA)


def bgr_to_rgb(frame: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)


def to_pil(frame_bgr: np.ndarray) -> Image.Image:
    rgb = bgr_to_rgb(frame_bgr)
    return Image.fromarray(rgb)


def pil_to_bgr(image: Image.Image) -> np.ndarray:
    rgb = np.array(image.convert("RGB"))
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def save_frame(frame_bgr: np.ndarray, output_dir: Path, prefix: str = "frame") -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = output_dir / f"{prefix}_{int(cv2.getTickCount())}.jpg"
    cv2.imwrite(str(filename), frame_bgr)
    return filename
