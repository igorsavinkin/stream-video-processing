"""Smoke tests for ML model inference."""

import io
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from src.config import Settings
from src.model.infer import load_model, predict_bgr, predict_pil


def _create_test_image(width: int = 224, height: int = 224) -> Image.Image:
    """Create a test RGB image."""
    return Image.new("RGB", (width, height), color=(128, 128, 128))


def _create_test_bgr_frame(width: int = 224, height: int = 224) -> np.ndarray:
    """Create a test BGR frame (numpy array)."""
    return np.zeros((height, width, 3), dtype=np.uint8)


@pytest.fixture
def mobilenet_settings():
    """Settings for MobileNetV3 model."""
    return Settings(
        model_name="mobilenet_v3_small",
        device="cpu",
        class_topk=5,
    )


@pytest.fixture
def person_detector_settings():
    """Settings for person detector model."""
    return Settings(
        model_name="person_detector",
        device="cpu",
        person_score_threshold=0.6,
    )


def test_load_model_mobilenet(mobilenet_settings):
    """Smoke test: Load MobileNetV3 model."""
    model, preprocess, categories, device, model_kind = load_model(mobilenet_settings)
    
    assert model is not None
    assert preprocess is not None
    assert len(categories) > 0
    assert device.type == "cpu"
    assert model_kind == "classifier"
    assert "golden_retriever" in categories or len(categories) == 1000  # ImageNet classes


def test_load_model_person_detector(person_detector_settings):
    """Smoke test: Load person detector model."""
    model, preprocess, categories, device, model_kind = load_model(person_detector_settings)
    
    assert model is not None
    assert preprocess is not None
    assert len(categories) > 0
    assert device.type == "cpu"
    assert model_kind == "detector"
    assert "person" in categories  # COCO dataset includes person class


def test_predict_pil_mobilenet(mobilenet_settings):
    """Smoke test: Run inference with MobileNetV3 on PIL image."""
    model, preprocess, categories, device, model_kind = load_model(mobilenet_settings)
    image = _create_test_image()
    
    results = predict_pil(
        model,
        preprocess,
        categories,
        device,
        image,
        topk=5,
        model_kind=model_kind,
    )
    
    assert isinstance(results, list)
    assert len(results) == 5
    assert all("label" in r and "score" in r for r in results)
    assert all(0.0 <= r["score"] <= 1.0 for r in results)
    assert all(isinstance(r["label"], str) for r in results)


def test_predict_bgr_mobilenet(mobilenet_settings):
    """Smoke test: Run inference with MobileNetV3 on BGR frame."""
    model, preprocess, categories, device, model_kind = load_model(mobilenet_settings)
    frame = _create_test_bgr_frame()
    
    results = predict_bgr(
        model,
        preprocess,
        categories,
        device,
        frame,
        topk=3,
        model_kind=model_kind,
    )
    
    assert isinstance(results, list)
    assert len(results) == 3
    assert all("label" in r and "score" in r for r in results)
    assert all(0.0 <= r["score"] <= 1.0 for r in results)


def test_predict_pil_person_detector(person_detector_settings):
    """Smoke test: Run inference with person detector on PIL image."""
    model, preprocess, categories, device, model_kind = load_model(person_detector_settings)
    image = _create_test_image()
    
    results = predict_pil(
        model,
        preprocess,
        categories,
        device,
        image,
        model_kind=model_kind,
        person_score_threshold=0.6,
    )
    
    assert isinstance(results, list)
    assert len(results) == 2
    assert all("label" in r and "score" in r for r in results)
    assert any(r["label"] == "person" for r in results)
    assert any(r["label"] == "no_person" for r in results)
    assert all(0.0 <= r["score"] <= 1.0 for r in results)


def test_predict_bgr_person_detector(person_detector_settings):
    """Smoke test: Run inference with person detector on BGR frame."""
    model, preprocess, categories, device, model_kind = load_model(person_detector_settings)
    frame = _create_test_bgr_frame()
    
    results = predict_bgr(
        model,
        preprocess,
        categories,
        device,
        frame,
        model_kind=model_kind,
        person_score_threshold=0.6,
    )
    
    assert isinstance(results, list)
    assert len(results) == 2
    assert all("label" in r and "score" in r for r in results)
    assert any(r["label"] == "person" for r in results)
    assert any(r["label"] == "no_person" for r in results)


def test_predict_topk_variation(mobilenet_settings):
    """Test that topk parameter works correctly."""
    model, preprocess, categories, device, model_kind = load_model(mobilenet_settings)
    image = _create_test_image()
    
    for topk in [1, 3, 5, 10]:
        results = predict_pil(
            model,
            preprocess,
            categories,
            device,
            image,
            topk=topk,
            model_kind=model_kind,
        )
        assert len(results) == topk
        # Scores should be in descending order
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)


def test_predict_different_image_sizes(mobilenet_settings):
    """Test inference with different image sizes."""
    model, preprocess, categories, device, model_kind = load_model(mobilenet_settings)
    
    for size in [(64, 64), (224, 224), (480, 360)]:
        image = _create_test_image(width=size[0], height=size[1])
        results = predict_pil(
            model,
            preprocess,
            categories,
            device,
            image,
            topk=3,
            model_kind=model_kind,
        )
        assert len(results) == 3
        assert all("label" in r and "score" in r for r in results)
