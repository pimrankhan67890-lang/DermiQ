# Dataset (for a real model)

This project ships with a **demo heuristic model** by default. For real accuracy, you must train a real model using labeled images.

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

After you have images, run:

- `python train.py --dataset data/train --epochs 8 --out-model models/skin_model.keras --out-labels models/labels.json`

If TensorFlow install fails, use Python **3.10/3.11** (TensorFlow may not support very new Python versions).

