from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List


IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def iter_images(dataset_dir: Path) -> List[Path]:
    return [p for p in dataset_dir.rglob("*") if p.is_file() and p.suffix.lower() in IMG_EXTS]


def infer_body_zone(relpath: str) -> str:
    value = relpath.lower()
    mapping = {
        "scalp": "scalp",
        "hair": "scalp",
        "face": "face",
        "cheek": "face",
        "forehead": "face",
        "chin": "face",
        "nose": "face",
        "neck": "neck",
        "chest": "trunk",
        "abdomen": "trunk",
        "back": "trunk",
        "arm": "arms",
        "hand": "hands",
        "finger": "hands",
        "leg": "legs",
        "thigh": "legs",
        "foot": "feet",
        "toe": "feet",
        "nail": "feet",
    }
    for key, label in mapping.items():
        if key in value:
            return label
    return "unknown"


def main() -> int:
    ap = argparse.ArgumentParser(description="Build a starter dataset manifest for DermIQ training.")
    ap.add_argument("--dataset", type=str, default="data/train", help="Folder with class subfolders.")
    ap.add_argument("--out", type=str, default="data/train_manifest.jsonl", help="Output manifest JSONL.")
    ap.add_argument("--source", type=str, default="internal_curated", help="Default source_dataset value.")
    args = ap.parse_args()

    dataset_dir = Path(args.dataset)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rows: List[Dict[str, str]] = []
    for path in sorted(iter_images(dataset_dir)):
        rel = path.relative_to(dataset_dir).as_posix()
        label = rel.split("/", 1)[0]
        rows.append(
            {
                "relpath": rel,
                "label": label,
                "body_zone": infer_body_zone(rel),
                "skin_tone_bucket": "unknown",
                "quality_flag": "needs_review",
                "source_dataset": str(args.source),
            }
        )

    out_path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + ("\n" if rows else ""), encoding="utf-8")
    print(f"Wrote {len(rows)} rows to {out_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
