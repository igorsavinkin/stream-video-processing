import numpy as np
from PIL import Image

from src.preprocess.transforms import (
    bgr_to_rgb,
    pil_to_bgr,
    resize_frame,
    save_frame,
    to_pil,
)


def test_bgr_to_rgb_roundtrip():
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    frame[:, :, 0] = 255
    rgb = bgr_to_rgb(frame)
    pil_img = to_pil(frame)
    assert isinstance(pil_img, Image.Image)
    roundtrip = pil_to_bgr(pil_img)
    assert rgb.shape == roundtrip.shape


def test_bgr_to_rgb_values():
    frame = np.zeros((1, 1, 3), dtype=np.uint8)
    frame[0, 0] = [0, 0, 255]  # pure red in BGR
    rgb = bgr_to_rgb(frame)
    assert rgb[0, 0].tolist() == [255, 0, 0]


def test_pil_to_bgr_roundtrip_values():
    frame = np.array([[[10, 20, 30], [40, 50, 60]]], dtype=np.uint8)
    pil_img = to_pil(frame)
    roundtrip = pil_to_bgr(pil_img)
    assert roundtrip.shape == frame.shape
    assert np.array_equal(roundtrip, frame)


def test_resize_frame_shape():
    frame = np.zeros((10, 20, 3), dtype=np.uint8)
    resized = resize_frame(frame, (5, 7))
    assert resized.shape == (7, 5, 3)


def test_save_frame_writes_file(tmp_path):
    frame = np.zeros((8, 8, 3), dtype=np.uint8)
    saved = save_frame(frame, tmp_path, prefix="test")
    assert saved.exists()
    assert saved.suffix == ".jpg"
