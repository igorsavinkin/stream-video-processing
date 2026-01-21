from __future__ import annotations

from typing import List, Tuple

import torch
from PIL import Image
from torchvision import models
from torchvision.models import MobileNet_V3_Small_Weights
from torchvision.models.detection import FasterRCNN_ResNet50_FPN_Weights

from src.config import Settings
from src.preprocess.transforms import to_pil


def load_model(
    settings: Settings,
) -> Tuple[torch.nn.Module, object, List[str], torch.device, str]:
    device = torch.device(settings.device)
    if settings.model_name in ("person_detector", "fasterrcnn_resnet50_fpn"):
        weights = FasterRCNN_ResNet50_FPN_Weights.DEFAULT
        model = models.detection.fasterrcnn_resnet50_fpn(weights=weights)
        categories = list(weights.meta.get("categories", []))
        preprocess = weights.transforms()
        model_kind = "detector"
    else:
        weights = MobileNet_V3_Small_Weights.DEFAULT
        model = models.mobilenet_v3_small(weights=weights)
        categories = list(weights.meta.get("categories", []))
        preprocess = weights.transforms()
        model_kind = "classifier"
    model.eval()
    model.to(device)
    return model, preprocess, categories, device, model_kind


@torch.inference_mode()
def predict_bgr(
    model: torch.nn.Module,
    preprocess,
    categories: List[str],
    device: torch.device,
    frame_bgr,
    topk: int = 5,
    model_kind: str = "classifier",
    person_score_threshold: float = 0.6,
) -> List[dict]:
    image = to_pil(frame_bgr)
    return predict_pil(
        model,
        preprocess,
        categories,
        device,
        image,
        topk=topk,
        model_kind=model_kind,
        person_score_threshold=person_score_threshold,
    )


@torch.inference_mode()
def predict_pil(
    model: torch.nn.Module,
    preprocess,
    categories: List[str],
    device: torch.device,
    image: Image.Image,
    topk: int = 5,
    model_kind: str = "classifier",
    person_score_threshold: float = 0.6,
) -> List[dict]:
    if model_kind == "detector":
        input_tensor = preprocess(image).to(device)
        outputs = model([input_tensor])[0]
        scores = outputs.get("scores")
        labels = outputs.get("labels")
        if scores is None or labels is None:
            return [{"label": "no_person", "score": 1.0}]
        person_label_idx = (
            categories.index("person") if "person" in categories else 1
        )
        person_scores = scores[labels == person_label_idx]
        best_score = float(person_scores.max().item()) if person_scores.numel() else 0.0
        has_person = best_score >= person_score_threshold
        return [
            {"label": "person", "score": round(best_score, 6)},
            {"label": "no_person", "score": 0.0 if has_person else 1.0},
        ]

    input_tensor = preprocess(image).unsqueeze(0).to(device)
    logits = model(input_tensor)
    probs = torch.softmax(logits, dim=1)[0]
    top_probs, top_idxs = torch.topk(probs, k=topk)
    results: List[dict] = []
    for score, idx in zip(top_probs.tolist(), top_idxs.tolist()):
        label = categories[idx] if idx < len(categories) else f"class_{idx}"
        results.append({"label": label, "score": round(score, 6)})
    return results
