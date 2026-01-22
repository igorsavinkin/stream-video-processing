## ML Model and Weights

The ML model comes from `torchvision` and is loaded with pretrained weights at app startup.
Specifically, in `src/model/infer.py` the default `torchvision` weights are used:
- Person detector (Faster R-CNN): `models.detection.fasterrcnn_resnet50_fpn(weights=FasterRCNN_ResNet50_FPN_Weights.DEFAULT)`
- Classifier: `models.mobilenet_v3_small(weights=MobileNet_V3_Small_Weights.DEFAULT)`

These weights are downloaded automatically on first run and cached by PyTorch
(typically `~/.cache/torch/hub/checkpoints`; on Windows `C:\Users\<user>\AppData\Local\...`).

The core libraries are installed from `requirements.txt`:
- `torch==2.9.1`
- `torchvision==0.24.1`

## ML Model and Device Selection

Model selection and device are controlled by settings in `src/config.py`:
- `model_name`
- `device`

Defaults:
- `device: cpu`
- In `config.example.yaml`:
  - `model_name: person_detector`
  - `device: cpu`

On API startup this configuration is loaded and logged in `src/api/app.py`
(`load_settings()` → `load_model()`).

## How to Change the ML Model or Device

YAML config:
- `model_name: person_detector` or `mobilenet_v3_small`
- `device: cuda` (only if CUDA is available)

Environment variables:
- `APP_MODEL_NAME=person_detector`
- `APP_DEVICE=cuda`

## Useful Notes

- When using the detector, predictions are a simple person/no_person result based on
  `person_score_threshold` from config.
- If the weights are already cached, startup is faster and no download occurs.
