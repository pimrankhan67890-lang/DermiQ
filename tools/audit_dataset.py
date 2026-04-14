from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List


IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def load_manifest(path: Path) -> Dict[str, Dict[str, str]]:
    if not path.exists():
        return {}
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return {}
    out: Dict[str, Dict[str, str]] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        if not isinstance(item, dict):
            continue
        rel = str(item.get("relpath", "")).replace("\\", "/").strip()
        if rel:
            out[rel] = {k: str(v).strip() for k, v in item.items() if k != "relpath"}
    return out


def iter_images(dataset_dir: Path) -> List[Path]:
    return [p for p in dataset_dir.rglob("*") if p.is_file() and p.suffix.lower() in IMG_EXTS]


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit DermIQ training data for whole-body readiness.")
    ap.add_argument("--dataset", type=str, default="data/train")
    ap.add_argument("--manifest", type=str, default="data/train_manifest.jsonl")
    ap.add_argument("--min-images-per-class", type=int, default=100)
    ap.add_argument("--min-classes", type=int, default=8)
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    dataset_dir = Path(args.dataset)
    manifest = load_manifest(Path(args.manifest))
    counts: Dict[str, int] = {}
    body_zone_coverage: Dict[str, int] = {}
    metadata_hits = 0
    total = 0

    for path in iter_images(dataset_dir):
        rel = path.relative_to(dataset_dir).as_posix()
        label = rel.split("/", 1)[0]
        counts[label] = counts.get(label, 0) + 1
        total += 1
        meta = manifest.get(rel, {})
        if meta.get("body_zone") and meta.get("quality_flag"):
            metadata_hits += 1
            zone = meta.get("body_zone", "unknown") or "unknown"
            body_zone_coverage[zone] = body_zone_coverage.get(zone, 0) + 1

    non_empty_classes = {k: v for k, v in sorted(counts.items()) if v > 0}
    weak = {k: v for k, v in non_empty_classes.items() if v < int(args.min_images_per_class)}
    metadata_coverage = (metadata_hits / total) if total else 0.0

    print("DermIQ dataset audit")
    print(f"  Total images: {total}")
    print(f"  Non-empty classes: {len(non_empty_classes)}")
    print(f"  Metadata coverage: {metadata_coverage:.1%}")
    print(f"  Body-zone coverage: {body_zone_coverage}")
    print(f"  Class counts: {non_empty_classes}")
    if weak:
        print(f"  Classes below threshold ({int(args.min_images_per_class)}): {weak}")

    failed = len(non_empty_classes) < int(args.min_classes) or bool(weak)
    if args.strict and failed:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
