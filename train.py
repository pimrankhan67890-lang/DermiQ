from __future__ import annotations

import argparse
import json
import random
import os
from pathlib import Path
from typing import Dict, List, Tuple


def find_class_folders(dataset_dir: Path) -> List[Path]:
    if not dataset_dir.exists():
        return []
    return sorted([p for p in dataset_dir.iterdir() if p.is_dir()])


def count_images(class_dir: Path) -> int:
    exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    count = 0
    for p in class_dir.rglob("*"):
        if p.is_file() and p.suffix.lower() in exts:
            count += 1
    return count


def dataset_summary(dataset_dir: Path) -> Tuple[List[str], int]:
    classes = find_class_folders(dataset_dir)
    labels = [c.name for c in classes]
    total = sum(count_images(c) for c in classes)
    return labels, total


def save_labels(labels: List[str], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"labels": labels}, indent=2), encoding="utf-8")


def load_manifest(path: Path) -> Dict[str, Dict[str, str]]:
    if not path.exists():
        return {}
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except Exception:
        return {}
    if not raw:
        return {}
    entries = []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            entries = parsed
    except Exception:
        entries = []
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except Exception:
                continue
    out: Dict[str, Dict[str, str]] = {}
    for item in entries:
        if not isinstance(item, dict):
            continue
        rel = str(item.get("relpath", "")).replace("\\", "/").strip()
        if not rel:
            continue
        out[rel] = {
            "body_zone": str(item.get("body_zone", "")).strip(),
            "skin_tone_bucket": str(item.get("skin_tone_bucket", "")).strip(),
            "quality_flag": str(item.get("quality_flag", "")).strip(),
            "source_dataset": str(item.get("source_dataset", "")).strip(),
        }
    return out


def non_empty_class_folders(dataset_dir: Path) -> List[Path]:
    classes = find_class_folders(dataset_dir)
    out: List[Path] = []
    for c in classes:
        if count_images(c) > 0:
            out.append(c)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Train a simple skin-condition image classifier (MVP).")
    parser.add_argument("--dataset", type=str, default="data/train", help="Folder with class subfolders.")
    parser.add_argument("--img-size", type=int, default=224, help="Square image size.")
    parser.add_argument("--batch", type=int, default=32, help="Batch size.")
    parser.add_argument("--epochs", type=int, default=8, help="Training epochs.")
    parser.add_argument("--finetune-epochs", type=int, default=2, help="Extra fine-tuning epochs (when using pretrained weights).")
    parser.add_argument("--val-split", type=float, default=0.2, help="Validation split fraction (stratified).")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    parser.add_argument("--out-model", type=str, default="models/skin_model.keras", help="Output model path.")
    parser.add_argument("--out-labels", type=str, default="models/labels.json", help="Output labels path.")
    parser.add_argument("--out-metrics", type=str, default="models/train_metrics.json", help="Output training metrics JSON.")
    parser.add_argument("--manifest", type=str, default="data/train_manifest.jsonl", help="Optional dataset metadata manifest.")
    parser.add_argument("--min-images-per-class", type=int, default=100, help="Minimum usable images per class for serious training.")
    parser.add_argument("--min-classes", type=int, default=8, help="Minimum number of non-empty classes for serious training.")
    parser.add_argument("--allow-small-dataset", action="store_true", help="Allow training to continue even if the dataset does not meet whole-body thresholds.")
    parser.add_argument("--require-manifest-metadata", action="store_true", help="Require metadata coverage in the manifest for serious training.")
    args = parser.parse_args()

    # Ensure Keras cache is writable (some environments block writing to user profile dirs).
    os.environ.setdefault("KERAS_HOME", str((Path.cwd() / ".keras_cache").resolve()))

    dataset_dir = Path(args.dataset)
    labels, total_images = dataset_summary(dataset_dir)

    if len(labels) < 2 or total_images < 10:
        print("Dataset not found (or too small) for training.")
        print("")
        print("Expected structure:")
        print("  data/train/<class_name>/*.jpg")
        print("")
        print("Minimum suggestion:")
        print("  - At least 2 classes")
        print("  - ~10+ images total (more is better)")
        print("")
        print(f"Looked in: {dataset_dir.resolve()}")
        print(f"Found classes: {labels}")
        print(f"Total images: {total_images}")
        print("")
        print("The Streamlit app still runs without a trained model (it uses a lightweight heuristic fallback).")
        return 0

    try:
        import tensorflow as tf  # type: ignore
    except Exception as e:
        print("TensorFlow is required to train the model, but it is not installed.")
        print(f"Error: {e}")
        print("")
        print("Install it, then rerun:")
        print("  pip install tensorflow")
        return 1

    img_size = (int(args.img_size), int(args.img_size))
    batch_size = int(args.batch)

    # Build datasets without Keras' directory indexing helper. On some locked-down Windows setups,
    # the internal queue/threadpool creation can fail with WinError 5. Manual indexing avoids that.
    class_dirs = non_empty_class_folders(dataset_dir)
    class_names = [p.name for p in class_dirs]
    if len(class_names) < 2:
        print("Dataset not found (or too small) for training.")
        print(f"Looked in: {dataset_dir.resolve()}")
        print(f"Found non-empty classes: {class_names}")
        return 0

    print(f"Classes: {class_names}")

    manifest = load_manifest(Path(args.manifest))
    class_counts = {name: count_images(dataset_dir / name) for name in class_names}
    weak_classes = {name: count for name, count in class_counts.items() if count < int(args.min_images_per_class)}
    serious_threshold_failed = len(class_names) < int(args.min_classes) or bool(weak_classes)

    metadata_coverage = 0.0
    if manifest:
        total_manifest_hits = 0
        metadata_hits = 0
        for class_dir in class_dirs:
            for p in class_dir.rglob("*"):
                if not p.is_file() or p.suffix.lower() not in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
                    continue
                rel = p.relative_to(dataset_dir).as_posix()
                if rel in manifest:
                    total_manifest_hits += 1
                    row = manifest[rel]
                    if row.get("body_zone") and row.get("quality_flag"):
                        metadata_hits += 1
        metadata_coverage = (metadata_hits / total_manifest_hits) if total_manifest_hits else 0.0
    elif args.require_manifest_metadata:
        metadata_coverage = 0.0

    if serious_threshold_failed and not args.allow_small_dataset:
        print("Dataset gate failed for whole-body training.")
        print(f"  Required non-empty classes: >= {int(args.min_classes)}")
        print(f"  Found non-empty classes: {len(class_names)}")
        if weak_classes:
            print(f"  Classes below {int(args.min_images_per_class)} images: {weak_classes}")
        print("  Add more licensed/permitted data or rerun with --allow-small-dataset for experimental training only.")
        return 1

    if args.require_manifest_metadata and metadata_coverage < 0.8 and not args.allow_small_dataset:
        print("Dataset metadata coverage is too low for serious whole-body training.")
        print(f"  Manifest coverage with body_zone + quality_flag: {metadata_coverage:.1%}")
        print("  Build a richer manifest first or rerun with --allow-small-dataset for experimental training only.")
        return 1

    all_paths: List[str] = []
    all_labels: List[int] = []
    for label_idx, class_dir in enumerate(class_dirs):
        exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
        for p in class_dir.rglob("*"):
            if p.is_file() and p.suffix.lower() in exts:
                all_paths.append(p.as_posix())
                all_labels.append(label_idx)

    # Stratified shuffle/split (helps small datasets).
    rng = random.Random(int(args.seed))
    by_class: List[List[int]] = [[] for _ in range(len(class_names))]
    for i, y in enumerate(all_labels):
        if 0 <= int(y) < len(by_class):
            by_class[int(y)].append(i)

    train_idxs: List[int] = []
    val_idxs: List[int] = []
    val_frac = float(args.val_split)
    val_frac = max(0.05, min(0.4, val_frac))

    for cls_idxs in by_class:
        rng.shuffle(cls_idxs)
        n = len(cls_idxs)
        n_val = max(1, int(round(n * val_frac))) if n >= 5 else max(1, int(n * val_frac))
        val_idxs.extend(cls_idxs[:n_val])
        train_idxs.extend(cls_idxs[n_val:])

    rng.shuffle(train_idxs)
    rng.shuffle(val_idxs)

    train_paths = [all_paths[i] for i in train_idxs]
    train_labels = [all_labels[i] for i in train_idxs]
    val_paths = [all_paths[i] for i in val_idxs]
    val_labels = [all_labels[i] for i in val_idxs]

    def load_and_preprocess(path: tf.Tensor, label: tf.Tensor):
        data = tf.io.read_file(path)
        img = tf.io.decode_image(data, channels=3, expand_animations=False)
        img = tf.cast(img, tf.float32)
        # Preserve aspect ratio to reduce distortion.
        img = tf.image.resize_with_pad(img, img_size[0], img_size[1], method="bilinear", antialias=True)
        return img, label

    autotune = tf.data.AUTOTUNE
    train_ds = (
        tf.data.Dataset.from_tensor_slices((train_paths, train_labels))
        .shuffle(buffer_size=min(10_000, len(train_paths)), seed=42, reshuffle_each_iteration=True)
        .map(load_and_preprocess, num_parallel_calls=autotune)
        .batch(batch_size)
        .prefetch(autotune)
    )
    val_ds = (
        tf.data.Dataset.from_tensor_slices((val_paths, val_labels))
        .map(load_and_preprocess, num_parallel_calls=autotune)
        .batch(batch_size)
        .prefetch(autotune)
    )

    print(f"Train batches: {tf.data.experimental.cardinality(train_ds).numpy()}")
    print(f"Val batches: {tf.data.experimental.cardinality(val_ds).numpy()}")

    # Cache to speed up CPU training.
    train_ds = train_ds.cache()
    val_ds = val_ds.cache()

    data_augmentation = tf.keras.Sequential(
        [
            tf.keras.layers.RandomFlip("horizontal"),
            tf.keras.layers.RandomRotation(0.05),
            tf.keras.layers.RandomZoom(0.1),
            tf.keras.layers.RandomContrast(0.12),
        ],
        name="augmentation",
    )

    # Try ImageNet weights; fall back to random init if unavailable (e.g., offline).
    try:
        base = tf.keras.applications.MobileNetV2(
            input_shape=(img_size[0], img_size[1], 3),
            include_top=False,
            weights="imagenet",
            pooling="avg",
        )
        base_note = "Using MobileNetV2 ImageNet weights."
        freeze_base = True
    except Exception as e:
        base = tf.keras.applications.MobileNetV2(
            input_shape=(img_size[0], img_size[1], 3),
            include_top=False,
            weights=None,
            pooling="avg",
        )
        base_note = f"Could not load ImageNet weights ({e}); using random init."
        freeze_base = False

    print(base_note)
    # If we couldn't load pretrained weights, freezing would make the model nearly random.
    base.trainable = not freeze_base

    inputs = tf.keras.Input(shape=(img_size[0], img_size[1], 3))
    x = data_augmentation(inputs)
    # Map [0, 255] -> [-1, 1] expected by MobileNetV2.
    x = tf.keras.layers.Rescaling(scale=2.0 / 255.0, offset=-1.0)(x)
    x = base(x, training=False)
    x = tf.keras.layers.Dropout(0.2)(x)
    outputs = tf.keras.layers.Dense(len(class_names), activation="softmax")(x)
    model = tf.keras.Model(inputs, outputs)

    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=1e-3 if freeze_base else 1e-4),
        loss=tf.keras.losses.SparseCategoricalCrossentropy(label_smoothing=0.05),
        metrics=[
            tf.keras.metrics.SparseCategoricalAccuracy(name="acc"),
            tf.keras.metrics.SparseTopKCategoricalAccuracy(k=3, name="top3"),
        ],
    )

    callbacks = [
        tf.keras.callbacks.EarlyStopping(monitor="val_acc", patience=4, restore_best_weights=True),
        tf.keras.callbacks.ReduceLROnPlateau(monitor="val_acc", patience=2, factor=0.5, min_lr=1e-6),
    ]

    # Class weights (helps imbalanced datasets).
    counts = [0 for _ in class_names]
    for y in train_labels:
        if 0 <= int(y) < len(counts):
            counts[int(y)] += 1
    total = float(sum(counts)) if sum(counts) else 1.0
    class_weight = {i: (total / max(1.0, float(c))) for i, c in enumerate(counts)}

    hist = model.fit(
        train_ds,
        validation_data=val_ds,
        epochs=int(args.epochs),
        callbacks=callbacks,
        class_weight=class_weight,
    )

    # Optional fine-tune: unfreeze top layers of the base when we had pretrained weights.
    finetune_epochs = max(0, int(args.finetune_epochs))
    if freeze_base and finetune_epochs > 0:
        base.trainable = True
        # Keep batch norm frozen for stability.
        for layer in base.layers:
            if isinstance(layer, tf.keras.layers.BatchNormalization):
                layer.trainable = False

        model.compile(
            optimizer=tf.keras.optimizers.Adam(learning_rate=1e-5),
            loss=tf.keras.losses.SparseCategoricalCrossentropy(label_smoothing=0.05),
            metrics=[
                tf.keras.metrics.SparseCategoricalAccuracy(name="acc"),
                tf.keras.metrics.SparseTopKCategoricalAccuracy(k=3, name="top3"),
            ],
        )
        ft_hist = model.fit(train_ds, validation_data=val_ds, epochs=finetune_epochs, class_weight=class_weight)
        # Merge histories for output.
        for k, v in (ft_hist.history or {}).items():
            hist.history.setdefault(k, [])
            hist.history[k].extend(list(v))

    out_model = Path(args.out_model)
    out_model.parent.mkdir(parents=True, exist_ok=True)
    model.save(out_model.as_posix())

    out_labels = Path(args.out_labels)
    save_labels(class_names, out_labels)

    # Save a small metrics JSON (training curves + final eval + confusion matrix).
    try:
        import numpy as np  # type: ignore

        y_true = []
        y_pred = []
        for xb, yb in val_ds:
            probs = model.predict(xb, verbose=0)
            probs = np.asarray(probs)
            y_true.extend([int(x) for x in yb.numpy().tolist()])
            y_pred.extend([int(x) for x in probs.argmax(axis=1).tolist()])

        cm = tf.math.confusion_matrix(y_true, y_pred, num_classes=len(class_names)).numpy().tolist()
        eval_out = model.evaluate(val_ds, verbose=0)
        metric_names = list(model.metrics_names or [])
        eval_map = {metric_names[i]: float(eval_out[i]) for i in range(min(len(metric_names), len(eval_out)))}

        out_metrics = Path(args.out_metrics)
        out_metrics.parent.mkdir(parents=True, exist_ok=True)
        out_metrics.write_text(
            json.dumps(
                {
                    "classes": class_names,
                    "train_samples": len(train_paths),
                    "val_samples": len(val_paths),
                    "class_weight": {str(k): float(v) for k, v in class_weight.items()},
                    "class_counts": class_counts,
                    "manifest_path": str(Path(args.manifest)),
                    "metadata_coverage": metadata_coverage,
                    "history": hist.history or {},
                    "val_eval": eval_map,
                    "confusion_matrix": cm,
                    "img_size": int(args.img_size),
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"  Metrics: {out_metrics.resolve()}")
    except Exception:
        pass

    print("")
    print("Saved:")
    print(f"  Model:  {out_model.resolve()}")
    print(f"  Labels: {out_labels.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
