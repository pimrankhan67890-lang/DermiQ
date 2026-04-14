from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Tuple


IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def _iter_images(class_dir: Path) -> List[Path]:
    return [p for p in class_dir.rglob("*") if p.is_file() and p.suffix.lower() in IMG_EXTS]


def _load_labels(labels_path: Path) -> List[str]:
    payload = json.loads(labels_path.read_text(encoding="utf-8"))
    labels = payload.get("labels", [])
    if not isinstance(labels, list) or not all(isinstance(x, str) for x in labels):
        raise ValueError("labels.json must contain {'labels': ['class1', ...]}")
    return [x.strip() for x in labels if x.strip()]


def _load_manifest(path: Path) -> Dict[str, Dict[str, str]]:
    if not path.exists():
        return {}
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return {}
    rows = []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            rows = parsed
    except Exception:
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    out: Dict[str, Dict[str, str]] = {}
    for item in rows:
        if not isinstance(item, dict):
            continue
        rel = str(item.get("relpath", "")).replace("\\", "/").strip()
        if rel:
            out[rel] = {
                "body_zone": str(item.get("body_zone", "")).strip(),
                "skin_tone_bucket": str(item.get("skin_tone_bucket", "")).strip(),
                "quality_flag": str(item.get("quality_flag", "")).strip(),
            }
    return out


@dataclass(frozen=True)
class Metrics:
    samples: int
    top1_acc: float
    top3_acc: float
    per_class_acc: Dict[str, float]
    confusion_matrix: List[List[int]]
    by_body_zone: Dict[str, float]
    by_skin_tone_bucket: Dict[str, float]


def main() -> int:
    ap = argparse.ArgumentParser(description="Evaluate a trained Keras model on a labeled folder dataset.")
    ap.add_argument("--dataset", type=str, default="data/train", help="Folder with class subfolders.")
    ap.add_argument("--model", type=str, default="models/skin_model.keras", help="Model path (.keras).")
    ap.add_argument("--labels", type=str, default="models/labels.json", help="Labels JSON (must match training order).")
    ap.add_argument("--img-size", type=int, default=224, help="Square image size used in training.")
    ap.add_argument("--batch", type=int, default=32, help="Batch size.")
    ap.add_argument("--out", type=str, default="models/eval_metrics.json", help="Output JSON path.")
    ap.add_argument("--manifest", type=str, default="data/train_manifest.jsonl", help="Optional dataset metadata manifest.")
    args = ap.parse_args()

    try:
        import numpy as np  # type: ignore
        import tensorflow as tf  # type: ignore
    except Exception as e:
        raise SystemExit(f"TensorFlow is required for evaluation. {e}")

    dataset_dir = Path(args.dataset)
    model_path = Path(args.model)
    labels_path = Path(args.labels)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest(Path(args.manifest))

    labels = _load_labels(labels_path)
    label_to_idx = {lbl: i for i, lbl in enumerate(labels)}

    # Load samples.
    all_paths: List[str] = []
    all_y: List[int] = []
    all_meta: List[Dict[str, str]] = []
    for lbl in labels:
        cdir = dataset_dir / lbl
        if not cdir.exists():
            continue
        for p in _iter_images(cdir):
            all_paths.append(p.as_posix())
            all_y.append(label_to_idx[lbl])
            rel = p.relative_to(dataset_dir).as_posix()
            all_meta.append(manifest.get(rel, {}))

    if not all_paths:
        raise SystemExit("No images found for the labels in labels.json.")

    model = tf.keras.models.load_model(model_path.as_posix())
    img_size = (int(args.img_size), int(args.img_size))
    batch = int(args.batch)

    def load_and_preprocess(path: tf.Tensor, label: tf.Tensor):
        data = tf.io.read_file(path)
        img = tf.io.decode_image(data, channels=3, expand_animations=False)
        img = tf.cast(img, tf.float32)
        img = tf.image.resize_with_pad(img, img_size[0], img_size[1], method="bilinear", antialias=True)
        # Match MobileNetV2 preprocessing: [0,255] -> [-1,1]
        img = (img * (2.0 / 255.0)) - 1.0
        return img, label

    ds = (
        tf.data.Dataset.from_tensor_slices((all_paths, all_y))
        .map(load_and_preprocess, num_parallel_calls=tf.data.AUTOTUNE)
        .batch(batch)
        .prefetch(tf.data.AUTOTUNE)
    )

    y_true = []
    y_pred = []
    y_top3 = []
    for xb, yb in ds:
        probs = model.predict(xb, verbose=0)
        probs = np.asarray(probs)
        pred = probs.argmax(axis=1).tolist()
        top3 = np.argsort(-probs, axis=1)[:, :3].tolist()
        y_true.extend([int(x) for x in yb.numpy().tolist()])
        y_pred.extend([int(x) for x in pred])
        y_top3.extend([[int(x) for x in row] for row in top3])

    n = len(y_true)
    top1 = sum(1 for a, b in zip(y_true, y_pred) if a == b) / float(n)
    top3 = sum(1 for a, row in zip(y_true, y_top3) if a in set(row)) / float(n)

    cm = tf.math.confusion_matrix(y_true, y_pred, num_classes=len(labels)).numpy().tolist()

    per_class: Dict[str, float] = {}
    for i, lbl in enumerate(labels):
        row = cm[i]
        denom = sum(int(x) for x in row)
        per_class[lbl] = (float(row[i]) / float(denom)) if denom else 0.0

    def slice_acc(key: str) -> Dict[str, float]:
        buckets: Dict[str, List[int]] = {}
        for idx, meta in enumerate(all_meta):
            bucket = str(meta.get(key, "")).strip() or "unknown"
            buckets.setdefault(bucket, []).append(idx)
        out: Dict[str, float] = {}
        for bucket, indices in buckets.items():
            if not indices:
                continue
            correct = sum(1 for i in indices if y_true[i] == y_pred[i])
            out[bucket] = float(correct / len(indices))
        return out

    m = Metrics(
        samples=n,
        top1_acc=float(top1),
        top3_acc=float(top3),
        per_class_acc=per_class,
        confusion_matrix=[[int(x) for x in r] for r in cm],
        by_body_zone=slice_acc("body_zone"),
        by_skin_tone_bucket=slice_acc("skin_tone_bucket"),
    )

    out_path.write_text(json.dumps(asdict(m), indent=2), encoding="utf-8")
    print(f"Saved: {out_path.resolve()}")
    print(f"Samples: {n}")
    print(f"Top-1 accuracy: {top1:.4f}")
    print(f"Top-3 accuracy: {top3:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
