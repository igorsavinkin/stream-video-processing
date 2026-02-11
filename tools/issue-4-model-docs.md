# Model Documentation Checklist

Add to Issue #4: "Runbook docs" (Iteration 1)

## Checklist items to add:

- [ ] Document default model (MobileNetV3 Small)
  - [ ] Explain it's an ImageNet-1K classifier (1000 classes)
  - [ ] Show example output format (top-k predictions with scores)
  - [ ] List common classes it recognizes (dog, cat, car, person, etc.)
  
- [ ] Document optional person detector (Faster R-CNN)
  - [ ] Explain it's a COCO-trained detector
  - [ ] Show how to enable it (`APP_MODEL_NAME=person_detector`)
  - [ ] Show example output format (person/no_person)
  
- [ ] Add model comparison table
  - [ ] When to use MobileNetV3 (general classification)
  - [ ] When to use person_detector (simple presence detection)
  
- [ ] Document model inference behavior
  - [ ] Input: single frame from video stream
  - [ ] Output: JSON with predictions
  - [ ] Top-k parameter (default: 5)
  
- [ ] Add section on fine-tuning (future)
  - [ ] How to collect dataset (`src/ingest/capture`)
  - [ ] How to train custom model (`src/model/train.py`)
  - [ ] Continuous Training (CT) workflow (Iteration 2)

## Notes:
- README.md has been updated with model documentation
- This checklist ensures runbook completeness for model usage
