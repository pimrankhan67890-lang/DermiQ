from __future__ import annotations

import argparse
import json
import random
import os
from pathlib import Path
from typing import List, Tuple


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
    parser.add_argument("--out-model", type=str, default="models/skin_model.keras", help="Output model path.")
    parser.add_argument("--out-labels", type=str, default="models/labels.json", help="Output labels path.")
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

    all_paths: List[str] = []
    all_labels: List[int] = []
    for label_idx, class_dir in enumerate(class_dirs):
        exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
        for p in class_dir.rglob("*"):
            if p.is_file() and p.suffix.lower() in exts:
                all_paths.append(p.as_posix())
                all_labels.append(label_idx)

    # Shuffle deterministically.
    rng = random.Random(42)
    idxs = list(range(len(all_paths)))
    rng.shuffle(idxs)
    all_paths = [all_paths[i] for i in idxs]
    all_labels = [all_labels[i] for i in idxs]

    # Simple split (80/20).
    split = max(1, int(len(all_paths) * 0.8))
    train_paths, val_paths = all_paths[:split], all_paths[split:]
    train_labels, val_labels = all_labels[:split], all_labels[split:]

    def load_and_preprocess(path: tf.Tensor, label: tf.Tensor):
        data = tf.io.read_file(path)
        img = tf.io.decode_image(data, channels=3, expand_animations=False)
        img = tf.cast(img, tf.float32)
        img = tf.image.resize(img, img_size, method="bilinear")
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
        loss=tf.keras.losses.SparseCategoricalCrossentropy(),
        metrics=["accuracy"],
    )

    callbacks = [
        tf.keras.callbacks.EarlyStopping(monitor="val_accuracy", patience=3, restore_best_weights=True),
    ]

    model.fit(train_ds, validation_data=val_ds, epochs=int(args.epochs), callbacks=callbacks)

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
            loss=tf.keras.losses.SparseCategoricalCrossentropy(),
            metrics=["accuracy"],
        )
        model.fit(train_ds, validation_data=val_ds, epochs=finetune_epochs)

    out_model = Path(args.out_model)
    out_model.parent.mkdir(parents=True, exist_ok=True)
    model.save(out_model.as_posix())

    out_labels = Path(args.out_labels)
    save_labels(class_names, out_labels)

    print("")
    print("Saved:")
    print(f"  Model:  {out_model.resolve()}")
    print(f"  Labels: {out_labels.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
