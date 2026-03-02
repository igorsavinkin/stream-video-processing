## ML Model and Weights

The ML model comes from `torchvision` and is loaded with pretrained weights at app startup.
In `src/model/infer.py` the default `torchvision` weights are used:

### Classifier models (ImageNet-1K, 1000 classes)

| Model | `model_name` | Top-1 Accuracy | Params | Notes |
|-------|-------------|----------------|--------|-------|
| ResNet-50 | `resnet50` | ~80.9% | 25M | **Default.** Best accuracy, recommended for production |
| EfficientNet-B0 | `efficientnet_b0` | ~77.7% | 5.3M | Good balance of accuracy and speed |
| MobileNetV3-Small | `mobilenet_v3_small` | ~67.7% | 2.5M | Fastest, but weakest accuracy — not recommended for general classification |

### Detector models

| Model | `model_name` | Notes |
|-------|-------------|-------|
| Faster R-CNN (ResNet-50 FPN) | `person_detector` | Returns only `person` / `no_person` |

These weights are downloaded automatically on first run and cached by PyTorch
(typically `~/.cache/torch/hub/checkpoints`; on Windows `C:\Users\<user>\AppData\Local\...`).

The core libraries are installed from `requirements.txt`:
- `torch==2.9.1`
- `torchvision==0.24.1`

## ML Model and Device Selection

Model selection and device are controlled by settings in `src/config.py`:
- `model_name` — which model to load (see table above)
- `device` — `cpu` or `cuda`

Defaults:
- `model_name: resnet50`
- `device: cpu`

On API startup this configuration is loaded and logged in `src/api/app.py`
(`load_settings()` → `load_model()`).

## How to Change the ML Model or Device

YAML config:
- `model_name: resnet50` (recommended) or `efficientnet_b0`, `mobilenet_v3_small`, `person_detector`
- `device: cuda` (only if CUDA is available)

Environment variables:
- `APP_MODEL_NAME=resnet50`
- `APP_DEVICE=cuda`

## Why ResNet-50 is the Default

MobileNetV3-Small was previously the default, but its low accuracy (~67.7%) caused
incorrect predictions on many real-world images (e.g., trees classified as "jigsaw puzzle",
people misclassified). ResNet-50 provides significantly better accuracy (~80.9%) while
still being fast enough for real-time inference on CPU.

## Useful Notes

- When using the detector, predictions are a simple person/no_person result based on
  `person_score_threshold` from config.
- If the weights are already cached, startup is faster and no download occurs.
- ImageNet does not have a generic "tree" class — it has specific tree species and
  scene categories. The classifier will return the closest matching ImageNet category.
