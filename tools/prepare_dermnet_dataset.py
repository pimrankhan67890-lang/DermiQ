from __future__ import annotations

import argparse
import random
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Sequence


IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


@dataclass(frozen=True)
class Rule:
    label: str
    src_dir: Path
    include: re.Pattern | None = None
    exclude: re.Pattern | None = None


def iter_images(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower() in IMG_EXTS:
            yield p


def filter_paths(paths: Sequence[Path], include: re.Pattern | None, exclude: re.Pattern | None) -> List[Path]:
    out: List[Path] = []
    for p in paths:
        name = p.name
        if include is not None and not include.search(name):
            continue
        if exclude is not None and exclude.search(name):
            continue
        out.append(p)
    return out


def copy_sample(
    *,
    paths: Sequence[Path],
    dst_dir: Path,
    max_images: int,
    seed: int,
) -> int:
    dst_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    pool = list(paths)
    rng.shuffle(pool)
    take = pool[: max(0, int(max_images))]

    copied = 0
    for src in take:
        # Keep original filename, but ensure uniqueness in destination.
        base = src.stem
        ext = src.suffix.lower()
        out = dst_dir / f"{base}{ext}"
        i = 2
        while out.exists():
            out = dst_dir / f"{base}_{i}{ext}"
            i += 1
        shutil.copy2(src, out)
        copied += 1
    return copied


def main() -> int:
    ap = argparse.ArgumentParser(description="Prepare a small, labeled training set from DermNet-style folders.")
    ap.add_argument("--dermnet-root", type=str, default="data/_incoming_archive/dermnet_data/train")
    ap.add_argument("--out", type=str, default="data/train")
    ap.add_argument("--max-per-class", type=int, default=500)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    dermnet_root = Path(args.dermnet_root)
    out_root = Path(args.out)
    max_per = int(args.max_per_class)
    seed = int(args.seed)

    # Mapping rules for the provided archive structure.
    rules = [
        Rule(
            label="acne",
            src_dir=dermnet_root / "Acne and Rosacea",
            include=re.compile(r"acne", re.IGNORECASE),
            exclude=re.compile(r"rosacea|rhinophyma", re.IGNORECASE),
        ),
        Rule(
            label="rosacea",
            src_dir=dermnet_root / "Acne and Rosacea",
            include=re.compile(r"rosacea|rhinophyma", re.IGNORECASE),
        ),
        Rule(label="eczema", src_dir=dermnet_root / "Eczema"),
        Rule(
            label="psoriasis",
            src_dir=dermnet_root / "Psoriasis pictures Lichen Planus and related diseases",
            include=re.compile(r"psoriasis", re.IGNORECASE),
        ),
        Rule(label="hyperpigmentation", src_dir=dermnet_root / "Light Diseases and Disorders of Pigmentation"),
    ]

    if not dermnet_root.exists():
        raise SystemExit(f"DermNet root not found: {dermnet_root.resolve()}")

    out_root.mkdir(parents=True, exist_ok=True)

    summary = []
    for idx, rule in enumerate(rules):
        all_imgs = list(iter_images(rule.src_dir))
        filtered = filter_paths(all_imgs, rule.include, rule.exclude)
        copied = copy_sample(
            paths=filtered,
            dst_dir=out_root / rule.label,
            max_images=max_per,
            seed=seed + idx,
        )
        summary.append((rule.label, len(all_imgs), len(filtered), copied))

    marker = out_root / "_prepared_from_dermnet.txt"
    marker.write_text(
        "Prepared dataset from DermNet archive.\n"
        f"Source: {dermnet_root.resolve()}\n"
        f"Max per class: {max_per}\n"
        "Summary (label, total_found, matched_rule, copied):\n"
        + "\n".join([f"- {lbl}: {total} found, {matched} matched, {copied} copied" for lbl, total, matched, copied in summary])
        + "\n",
        encoding="utf-8",
    )

    print(marker.read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

