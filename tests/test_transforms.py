import numpy as np
from PIL import Image

from src.preprocess.transforms import bgr_to_rgb, pil_to_bgr, to_pil


def test_bgr_to_rgb_roundtrip():
    frame = np.zeros((10, 10, 3), dtype=np.uint8)
    frame[:, :, 0] = 255
    rgb = bgr_to_rgb(frame)
    pil_img = to_pil(frame)
    assert isinstance(pil_img, Image.Image)
    roundtrip = pil_to_bgr(pil_img)
    assert rgb.shape == roundtrip.shape
