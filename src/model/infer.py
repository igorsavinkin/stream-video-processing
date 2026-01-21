from __future__ import annotations

from typing import List, Tuple

import torch
from PIL import Image
from torchvision import models
from torchvision.models import MobileNet_V3_Small_Weights

from src.config import Settings
from src.preprocess.transforms import to_pil


def load_model(settings: Settings) -> Tuple[torch.nn.Module, object, List[str], torch.device]:
    device = torch.device(settings.device)
    weights = MobileNet_V3_Small_Weights.DEFAULT
    model = models.mobilenet_v3_small(weights=weights)
    model.eval()
    model.to(device)
    categories = list(weights.meta.get("categories", []))
    preprocess = weights.transforms()
    return model, preprocess, categories, device


@torch.inference_mode()
def predict_bgr(
    model: torch.nn.Module,
    preprocess,
    categories: List[str],
    device: torch.device,
    frame_bgr,
    topk: int = 5,
) -> List[dict]:
    image = to_pil(frame_bgr)
    return predict_pil(model, preprocess, categories, device, image, topk=topk)


@torch.inference_mode()
def predict_pil(
    model: torch.nn.Module,
    preprocess,
    categories: List[str],
    device: torch.device,
    image: Image.Image,
    topk: int = 5,
) -> List[dict]:
    input_tensor = preprocess(image).unsqueeze(0).to(device)
    logits = model(input_tensor)
    probs = torch.softmax(logits, dim=1)[0]
    top_probs, top_idxs = torch.topk(probs, k=topk)
    results: List[dict] = []
    for score, idx in zip(top_probs.tolist(), top_idxs.tolist()):
        label = categories[idx] if idx < len(categories) else f"class_{idx}"
        results.append({"label": label, "score": round(score, 6)})
    return results
