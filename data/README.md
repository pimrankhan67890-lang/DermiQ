# Dataset (for a real model)

This project ships with a **demo heuristic model** by default. For real accuracy, you must train a real model using labeled, permitted images.

## Folder structure

Create folders like this (folder name = label):

```
data/
  train/
    acne/
    eczema/
    rosacea/
    psoriasis/
    hyperpigmentation/
    dryness/
    seborrheic_dermatitis/
    normal/
```

Put images inside each folder:

```
data/train/acne/img001.jpg
data/train/acne/img002.jpg
...
```

## Training

Before serious whole-body training, build a metadata manifest and audit the dataset:

- `python tools/build_dataset_manifest.py --dataset data/train --out data/train_manifest.jsonl`
- `python tools/audit_dataset.py --dataset data/train --manifest data/train_manifest.jsonl --strict`

After you have enough images, run:

- `python train.py --dataset data/train --manifest data/train_manifest.jsonl --epochs 8 --out-model models/skin_model.keras --out-labels models/labels.json --require-manifest-metadata`

Manifest fields per image:

- `label`
- `body_zone`
- `skin_tone_bucket`
- `quality_flag`
- `source_dataset`

If TensorFlow install fails, use Python **3.10/3.11** (TensorFlow may not support very new Python versions).
