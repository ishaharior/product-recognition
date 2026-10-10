"""Dataset inspection, conversion, splitting & merging utilities
(opt-in; nothing downloads here).

Supported annotation formats
----------------------------
* ``yolo`` — one ``<class> cx cy w h`` text file per image (normalised 0..1)
* ``voc``  — PASCAL VOC XML (``<annotation><object><bndbox>…``)
* ``coco`` — COCO-style JSON (``images`` / ``annotations`` / ``categories``)

Anything else raises :class:`DatasetError` listing the supported formats —
the module never guesses or fabricates annotations.

Multiple YOLO datasets can be combined with :func:`merge_yolo_datasets`
(class-id remapping, cross-source duplicate removal, split preservation)
to build more diverse training corpora from several public sources.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


class DatasetError(RuntimeError):
    """Raised for unsupported or malformed dataset layouts."""


@dataclass
class InspectionReport:
    root: str
    detected_format: str
    image_count: int = 0
    label_count: int = 0
    missing_labels: list[str] = field(default_factory=list)
    orphan_labels: list[str] = field(default_factory=list)
    corrupt_images: list[str] = field(default_factory=list)
    invalid_label_lines: list[str] = field(default_factory=list)
    class_counts: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        if self.detected_format == "unsupported":
            return False
        return not (self.missing_labels or self.corrupt_images or self.invalid_label_lines)

    def to_dict(self) -> dict:
        return {
            "root": self.root,
            "detected_format": self.detected_format,
            "image_count": self.image_count,
            "label_count": self.label_count,
            "missing_labels": self.missing_labels[:50],
            "orphan_labels": self.orphan_labels[:50],
            "corrupt_images": self.corrupt_images[:50],
            "invalid_label_lines": self.invalid_label_lines[:50],
            "class_counts": dict(self.class_counts),
            "notes": self.notes,
            "ok": self.ok,
        }


# --------------------------------------------------------------------------- detection
def detect_format(root: Path) -> str:
    """Best-effort detection: 'yolo' | 'voc' | 'coco' | 'unsupported'."""
    root = Path(root)
    if not root.is_dir():
        raise DatasetError(f"Dataset directory not found: {root}")

    json_files = sorted(root.glob("*.json")) + sorted(root.glob("annotations/*.json"))
    for jf in json_files:
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if isinstance(data, dict) and "images" in data and "annotations" in data:
            return "coco"

    xml_files = sorted(root.glob("*.xml")) + sorted(root.glob("Annotations/*.xml")) + sorted(
        root.glob("annotations/*.xml")
    )
    for xf in xml_files:
        try:
            head = xf.read_text(encoding="utf-8", errors="ignore")[:400]
        except OSError:
            continue
        if "<annotation" in head:
            return "voc"

    if _has_yolo_layout(root):
        return "yolo"
    return "unsupported"


def _has_yolo_layout(root: Path) -> bool:
    images_dir = _find_dir(root, "images")
    labels_dir = _find_dir(root, "labels")
    if images_dir and labels_dir:
        return True
    # images and labels side by side: img.jpg + img.txt
    images = [p for ext in IMAGE_EXTS for p in root.glob(f"*{ext}")]
    txts = list(root.glob("*.txt"))
    return bool(images and txts)


def _find_dir(root: Path, name: str) -> Path | None:
    direct = root / name
    if direct.is_dir():
        return direct
    for sub in sorted(root.iterdir()) if root.is_dir() else []:
        if sub.is_dir() and sub.name.lower() == name:
            return sub
        nested = sub / name
        if sub.is_dir() and nested.is_dir():
            return nested
    return None


# --------------------------------------------------------------------------- inspection
def inspect_dataset(root: Path) -> InspectionReport:
    """Scan images + labels, detect problems and summarise class counts."""
    root = Path(root)
    fmt = detect_format(root)
    report = InspectionReport(root=str(root), detected_format=fmt)
    if fmt == "unsupported":
        report.notes.append(
            "Unsupported dataset layout. Supported formats: YOLO (txt), VOC (xml), COCO (json). "
            "See docs/DATASETS.md."
        )
        return report

    if fmt == "coco":
        _inspect_coco(root, report)
    elif fmt == "voc":
        _inspect_voc(root, report)
    else:
        _inspect_yolo(root, report)
    _check_images(root, report)
    return report


def _check_images(root: Path, report: InspectionReport) -> None:
    """Flag images that cannot be decoded (truncated/corrupt files)."""
    import cv2
    import numpy as np

    for img in _iter_images(root):
        try:
            data = np.fromfile(str(img), dtype=np.uint8)
            if data.size == 0 or cv2.imdecode(data, cv2.IMREAD_COLOR) is None:
                report.corrupt_images.append(str(img.relative_to(root)))
        except OSError:
            report.corrupt_images.append(str(img.relative_to(root)))


def _iter_images(root: Path) -> list[Path]:
    images: list[Path] = []
    for ext in IMAGE_EXTS:
        images.extend(root.rglob(f"*{ext}"))
        images.extend(root.rglob(f"*{ext.upper()}"))
    return sorted(set(images))


def _inspect_yolo(root: Path, report: InspectionReport) -> InspectionReport:
    images = _iter_images(root)
    labels_dir = _find_dir(root, "labels")
    report.image_count = len(images)
    class_counter: Counter[str] = Counter()

    for img in images:
        label_path = _label_path_for(img, root, labels_dir)
        if label_path is None or not label_path.exists():
            report.missing_labels.append(str(img.relative_to(root)))
            continue
        report.label_count += 1
        try:
            lines = label_path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            report.invalid_label_lines.append(f"{label_path.name}: not UTF-8 text")
            continue
        for idx, line in enumerate(lines, 1):
            line = line.strip()
            if not line:
                continue
            problem = _validate_yolo_line(line)
            if problem:
                report.invalid_label_lines.append(f"{label_path.name}:{idx}: {problem}")
            else:
                class_counter[line.split()[0]] += 1

    # orphan labels (txt without matching image)
    if labels_dir and labels_dir.is_dir():
        for txt in labels_dir.rglob("*.txt"):
            if not _image_path_for_label(txt, root, labels_dir, images).exists():
                report.orphan_labels.append(str(txt.relative_to(root)))

    report.class_counts = dict(sorted(class_counter.items(), key=lambda kv: -kv[1]))
    if not class_counter:
        report.notes.append("No class rows found in labels — check the layout.")
    return report


def _validate_yolo_line(line: str) -> str | None:
    parts = line.split()
    if len(parts) != 5:
        return f"expected 5 fields, got {len(parts)}"
    try:
        cls = int(parts[0])
        cx, cy, w, h = (float(p) for p in parts[1:])
    except ValueError:
        return "non-numeric values"
    if cls < 0:
        return "negative class id"
    if not (0.0 <= cx <= 1.0 and 0.0 <= cy <= 1.0 and 0.0 < w <= 1.0 and 0.0 < h <= 1.0):
        return "coordinates must be normalised to 0..1"
    return None


def _label_path_for(img: Path, root: Path, labels_dir: Path | None) -> Path | None:
    if labels_dir is None:
        return img.with_suffix(".txt")
    try:
        rel = img.relative_to(root)
    except ValueError:
        return img.with_suffix(".txt")
    parts = list(rel.parts)
    if parts and parts[0].lower() in {"images", "imgs"}:
        parts = parts[1:]
    candidate = labels_dir.joinpath(*parts).with_suffix(".txt")
    return candidate


def _image_path_for_label(txt: Path, root: Path, labels_dir: Path, images: list[Path]) -> Path:
    try:
        rel = txt.relative_to(labels_dir)
    except ValueError:
        return txt.with_suffix(".jpg")
    images_dir = _find_dir(root, "images")
    if images_dir:
        return images_dir.joinpath(rel).with_suffix(".jpg")
    return root.joinpath(rel).with_suffix(".jpg")


def _inspect_voc(root: Path, report: InspectionReport) -> InspectionReport:
    xmls = sorted(root.rglob("*.xml"))
    report.image_count = len(_iter_images(root))
    class_counter: Counter[str] = Counter()
    for xf in xmls:
        try:
            tree = ET.parse(xf)
        except ET.ParseError:
            report.invalid_label_lines.append(f"{xf.name}: invalid XML")
            continue
        for obj in tree.getroot().findall("object"):
            name = obj.findtext("name")
            if not name:
                report.invalid_label_lines.append(f"{xf.name}: <object> without <name>")
                continue
            bbox = obj.find("bndbox")
            if bbox is None:
                report.invalid_label_lines.append(f"{xf.name}: <object> without <bndbox>")
                continue
            class_counter[name.strip()] += 1
    report.label_count = len(xmls)
    report.class_counts = dict(sorted(class_counter.items(), key=lambda kv: -kv[1]))
    return report


def _inspect_coco(root: Path, report: InspectionReport) -> InspectionReport:
    images, anns, cats = _load_coco(root)
    report.image_count = len(images)
    report.label_count = len(images)
    class_counter: Counter[str] = Counter()
    cat_names = {c["id"]: c["name"] for c in cats}
    for ann in anns:
        class_counter[str(cat_names.get(ann.get("category_id"), ann.get("category_id")))] += 1
    report.class_counts = dict(sorted(class_counter.items(), key=lambda kv: -kv[1]))
    return report


def _load_coco(root: Path) -> tuple[list, list, list]:
    for jf in sorted(root.rglob("*.json")):
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if isinstance(data, dict) and "images" in data and "annotations" in data:
            return data["images"], data["annotations"], data.get("categories", [])
    raise DatasetError("No COCO annotation JSON (needs 'images' and 'annotations') found.")


# --------------------------------------------------------------------------- conversion
def convert_to_yolo(src: Path, dst: Path, fmt: str | None = None, class_names: list[str] | None = None) -> dict:
    """Convert a supported dataset into YOLO layout under *dst*.

    Produces ``dst/images/*.jpg|png`` and ``dst/labels/*.txt`` plus
    ``dst/classes.txt``. Returns a summary dict. Raises :class:`DatasetError`
    for unsupported formats — never invents annotations.
    """
    src, dst = Path(src), Path(dst)
    fmt = fmt or detect_format(src)
    if fmt == "unsupported":
        raise DatasetError(
            "Unsupported dataset format. Supported: 'yolo' (txt), 'voc' (xml), 'coco' (json). "
            "Inspect the source first with inspect_dataset()."
        )
    (dst / "images").mkdir(parents=True, exist_ok=True)
    (dst / "labels").mkdir(parents=True, exist_ok=True)

    if fmt == "yolo":
        return _convert_yolo(src, dst)
    if fmt == "voc":
        return _convert_voc(src, dst, class_names)
    if fmt == "coco":
        return _convert_coco(src, dst, class_names)
    raise DatasetError(f"Unknown format: {fmt}")


def _copy_image(img: Path, dst_images: Path) -> Path:
    target = dst_images / img.name
    if target.exists() and target.resolve() != img.resolve():
        target = dst_images / f"{img.parent.name}_{img.name}"
    shutil.copy2(img, target)
    return target


def _convert_yolo(src: Path, dst: Path) -> dict:
    images = _iter_images(src)
    labels_dir = _find_dir(src, "labels")
    copied = 0
    classes: set[str] = set()
    for img in images:
        label = _label_path_for(img, src, labels_dir)
        if label is None or not label.exists():
            continue
        out_img = _copy_image(img, dst / "images")
        shutil.copy2(label, (dst / "labels" / out_img.stem).with_suffix(".txt"))
        for line in label.read_text(encoding="utf-8").splitlines():
            if line.strip():
                classes.add(line.split()[0])
        copied += 1
    _write_classes(dst, sorted(classes, key=lambda c: int(c) if c.isdigit() else 0))
    return {"format": "yolo", "images": copied, "classes": sorted(classes)}


def _resolve_class_index(name: str, class_names: list[str] | None, mapping: dict[str, int]) -> int:
    if name in mapping:
        return mapping[name]
    if class_names and name in class_names:
        return class_names.index(name)
    index = len(mapping)
    mapping[name] = index
    return index


def _write_classes(dst: Path, classes: list[str]) -> None:
    (dst / "classes.txt").write_text("\n".join(classes) + "\n", encoding="utf-8")


def _convert_voc(src: Path, dst: Path, class_names: list[str] | None) -> dict:
    images_by_name = {p.name: p for p in _iter_images(src)}
    mapping: dict[str, int] = {}
    converted = 0
    for xf in sorted(src.rglob("*.xml")):
        try:
            root_el = ET.parse(xf).getroot()
        except ET.ParseError:
            continue
        filename = root_el.findtext("filename")
        if not filename:
            continue
        img = images_by_name.get(Path(filename).name)
        if img is None:
            continue
        size = root_el.find("size")
        if size is None:
            continue
        width = float(size.findtext("width") or 0)
        height = float(size.findtext("height") or 0)
        if width <= 0 or height <= 0:
            continue
        rows = []
        for obj in root_el.findall("object"):
            name = (obj.findtext("name") or "").strip()
            bbox = obj.find("bndbox")
            if not name or bbox is None:
                continue
            xmin = float(bbox.findtext("xmin") or 0)
            ymin = float(bbox.findtext("ymin") or 0)
            xmax = float(bbox.findtext("xmax") or 0)
            ymax = float(bbox.findtext("ymax") or 0)
            cx = ((xmin + xmax) / 2.0) / width
            cy = ((ymin + ymax) / 2.0) / height
            bw = (xmax - xmin) / width
            bh = (ymax - ymin) / height
            if not (0 < bw <= 1 and 0 < bh <= 1):
                continue
            cls = _resolve_class_index(name, class_names, mapping)
            rows.append(f"{cls} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")
        out_img = _copy_image(img, dst / "images")
        (dst / "labels" / f"{out_img.stem}.txt").write_text("\n".join(rows), encoding="utf-8")
        converted += 1
    names = _names_from_mapping(mapping, class_names)
    _write_classes(dst, names)
    return {"format": "voc", "images": converted, "classes": names}


def _convert_coco(src: Path, dst: Path, class_names: list[str] | None) -> dict:
    images, anns, cats = _load_coco(src)
    images_by_id = {img["id"]: img for img in images}
    cat_ids = sorted(c["id"] for c in cats)
    cat_names = {c["id"]: c["name"] for c in cats}
    id_to_index = {cid: i for i, cid in enumerate(cat_ids)}
    by_image: dict[int, list] = defaultdict(list)
    for ann in anns:
        by_image[ann["image_id"]].append(ann)

    images_root = _find_dir(src, "images") or src
    converted = 0
    for img in images_by_id.values():
        file_name = img.get("file_name", "")
        candidates = [images_root / file_name, src / file_name, src / Path(file_name).name]
        img_path = next((c for c in candidates if c.exists()), None)
        if img_path is None:
            found = list(src.rglob(Path(file_name).name))
            img_path = found[0] if found else None
        if img_path is None:
            continue
        width = float(img.get("width") or 0)
        height = float(img.get("height") or 0)
        if width <= 0 or height <= 0:
            continue
        rows = []
        for ann in by_image.get(img["id"], []):
            bbox = ann.get("bbox")  # [x, y, w, h] absolute
            if not bbox or len(bbox) != 4:
                continue
            x, y, w, h = (float(v) for v in bbox)
            cx = (x + w / 2.0) / width
            cy = (y + h / 2.0) / height
            nw, nh = w / width, h / height
            if not (0 < nw <= 1 and 0 < nh <= 1):
                continue
            cls = id_to_index.get(ann.get("category_id"))
            if cls is None:
                continue
            rows.append(f"{cls} {cx:.6f} {cy:.6f} {nw:.6f} {nh:.6f}")
        out_img = _copy_image(img_path, dst / "images")
        (dst / "labels" / f"{out_img.stem}.txt").write_text("\n".join(rows), encoding="utf-8")
        converted += 1
    names = [cat_names[cid] for cid in cat_ids] if cats else []
    if class_names:
        names = class_names
    _write_classes(dst, names)
    return {"format": "coco", "images": converted, "classes": names}


def _names_from_mapping(mapping: dict[str, int], class_names: list[str] | None) -> list[str]:
    if class_names:
        return class_names
    if not mapping:
        return []
    size = max(mapping.values()) + 1
    names = [""] * size
    for name, idx in mapping.items():
        names[idx] = name
    return names


# --------------------------------------------------------------------------- splitting
def deterministic_split(
    root: Path,
    output: Path,
    ratios: tuple[float, float, float] = (0.8, 0.1, 0.1),
    seed: int = 42,
) -> dict:
    """Leakage-free split: each *image* is assigned to exactly one subset by a
    stable hash of its path, so re-running with the same seed reproduces the
    split and no image can appear in two subsets.
    """
    if abs(sum(ratios) - 1.0) > 1e-6:
        raise DatasetError(f"Split ratios must sum to 1.0, got {sum(ratios)}")
    root, output = Path(root), Path(output)
    images = _iter_images(root)
    if not images:
        raise DatasetError(f"No images found under {root}")
    labels_dir = _find_dir(root, "labels")

    counts = {"train": 0, "val": 0, "test": 0}
    order = sorted(images, key=lambda p: p.as_posix())
    bounds = (ratios[0], ratios[0] + ratios[1])
    for img in order:
        digest = hashlib.sha256(f"{seed}:{img.as_posix()}".encode()).digest()
        bucket = int.from_bytes(digest[:4], "big") / 0xFFFFFFFF
        subset = "train" if bucket < bounds[0] else ("val" if bucket < bounds[1] else "test")
        for sub in ("images", "labels"):
            (output / subset / sub).mkdir(parents=True, exist_ok=True)
        _copy_image(img, output / subset / "images")
        label = _label_path_for(img, root, labels_dir)
        if label is not None and label.exists():
            shutil.copy2(label, (output / subset / "labels" / img.stem).with_suffix(".txt"))
        counts[subset] += 1
    if counts["val"] == 0 or counts["train"] == 0:
        raise DatasetError(
            f"Split produced an empty subset ({counts}) — dataset too small for these ratios."
        )
    return {"seed": seed, "ratios": list(ratios), "counts": counts}


# --------------------------------------------------------------------------- merging
def _load_yolo_class_names(src: Path) -> list[str]:
    """Class names for a YOLO dataset root: ``classes.txt`` or a dataset yaml."""
    classes_file = src / "classes.txt"
    if classes_file.exists():
        names = [
            line.strip()
            for line in classes_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        if names:
            return names
    for yml in ("dataset.yaml", "data.yaml", "dataset.yml", "data.yml"):
        path = src / yml
        if not path.exists():
            continue
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover - PyYAML is a dependency
            raise DatasetError("PyYAML is required to read dataset yaml files.") from exc
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise DatasetError(f"{path}: invalid YAML ({exc})") from exc
        raw = data.get("names") if isinstance(data, dict) else None
        if isinstance(raw, list):
            return [str(n).strip() for n in raw if str(n).strip()]
        if isinstance(raw, dict):
            try:
                ordered = sorted(raw.items(), key=lambda kv: int(kv[0]))
            except (TypeError, ValueError) as exc:
                raise DatasetError(f"{path}: 'names' keys must be integers") from exc
            return [str(v).strip() for _, v in ordered if str(v).strip()]
    raise DatasetError(
        f"{src}: no class names found — expected classes.txt or dataset.yaml/data.yaml "
        "with a 'names' list (run prepare_dataset.py config on the source first)."
    )


def _merge_layout(root: Path) -> str:
    """``'split'`` when ``train|val|test`` image dirs exist, else ``'flat'``."""
    for subset in ("train", "val", "test"):
        if (root / subset / "images").is_dir() or (root / "images" / subset).is_dir():
            return "split"
    if (root / "images").is_dir():
        return "flat"
    raise DatasetError(
        f"{root}: not a recognised YOLO layout "
        "(need images/ or train|val|test/images/)."
    )


def _images_in(directory: Path) -> list[Path]:
    return sorted(
        {p for ext in IMAGE_EXTS for p in directory.glob(f"*{ext}")},
        key=lambda p: p.name,
    )


def _collect_yolo_entries(src: Path) -> list[tuple[str, Path, Path | None]]:
    """Yield ``(split, image, label_or_None)`` for a YOLO root (both layouts)."""
    layout = _merge_layout(src)
    entries: list[tuple[str, Path, Path | None]] = []
    seen: set[Path] = set()

    if layout == "split":
        for subset in ("train", "val", "test"):
            a_img, a_lbl = src / subset / "images", src / subset / "labels"
            b_img, b_lbl = src / "images" / subset, src / "labels" / subset
            if a_img.is_dir():
                img_dir, lbl_dir = a_img, a_lbl
            elif b_img.is_dir():
                img_dir, lbl_dir = b_img, b_lbl
            else:
                continue
            for img in _images_in(img_dir):
                label = lbl_dir / f"{img.stem}.txt"
                entries.append((subset, img, label if label.exists() else None))
                seen.add(img)

    flat_dir = src / "images"
    if flat_dir.is_dir():
        for img in _images_in(flat_dir):
            if img in seen:
                continue
            label = src / "labels" / f"{img.stem}.txt"
            entries.append(("", img, label if label.exists() else None))

    if not entries:
        raise DatasetError(f"{src}: no YOLO images found.")
    return entries


def _file_fingerprint(path: Path) -> str:
    """Cheap content fingerprint: size + SHA-256 of the first 512 KiB."""
    size = path.stat().st_size
    digest = hashlib.sha256(str(size).encode())
    with path.open("rb") as fh:
        digest.update(fh.read(512 * 1024))
    return digest.hexdigest()


def _merge_copy_image(img: Path, dst_dir: Path, prefix: str) -> Path:
    target = dst_dir / img.name
    if target.exists():
        target = dst_dir / f"{prefix}_{img.name}"
        counter = 2
        while target.exists():
            target = dst_dir / f"{prefix}_{counter}_{img.name}"
            counter += 1
    shutil.copy2(img, target)
    return target


def _remap_label_file(label: Path, remap: dict[int, int], src: Path) -> str:
    out_lines: list[str] = []
    text = label.read_text(encoding="utf-8")
    for lineno, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        try:
            old_id = int(parts[0])
        except ValueError as exc:
            raise DatasetError(f"{label}:{lineno}: non-numeric class id {parts[0]!r}") from exc
        if old_id not in remap:
            raise DatasetError(
                f"{label}:{lineno}: class id {old_id} is not defined for {src} "
                f"({len(remap)} classes listed)."
            )
        out_lines.append(f"{remap[old_id]} " + " ".join(parts[1:]))
    return "".join(f"{line}\n" for line in out_lines)


def merge_yolo_datasets(inputs: list[Path], output: Path) -> dict:
    """Combine several YOLO datasets into one ready-to-train dataset.

    * Unions the per-input class names (stable first-seen order) and rewrites
      every label with the remapped class ids — never guesses missing names.
    * Preserves existing ``train/val/test`` splits; unsplit (flat) inputs are
      placed in ``train/`` when at least one input is split, otherwise the
      output stays flat and the caller should run ``split`` next.
    * Removes cross-source duplicates by content fingerprint (leakage guard:
      the same picture shipped with two datasets cannot land in two subsets).
    * Skips images that have no label file (counted, not silently ignored).

    Returns a summary dict; raises :class:`DatasetError` on missing inputs,
    missing class names, undefined class ids, or an unusable merged split.
    """
    inputs = [Path(p) for p in inputs]
    output = Path(output)
    if len(inputs) < 2:
        raise DatasetError("merge needs at least two input datasets.")
    for src in inputs:
        if not src.is_dir():
            raise DatasetError(f"Input dataset not found: {src}")
        if output.resolve() == src.resolve() or src.resolve() in output.resolve().parents:
            raise DatasetError(f"Output {output} must not live inside input {src}.")
    if output.exists() and any(output.iterdir()):
        raise DatasetError(f"Output directory {output} already exists and is not empty.")

    # Union of class names → per-input class-id remaps.
    class_names: list[str] = []
    remaps: list[dict[int, int]] = []
    for src in inputs:
        names = _load_yolo_class_names(src)
        remap: dict[int, int] = {}
        for old_id, name in enumerate(names):
            if name not in class_names:
                class_names.append(name)
            remap[old_id] = class_names.index(name)
        remaps.append(remap)

    layouts = [_merge_layout(src) for src in inputs]
    split_mode = "split" in layouts

    counts = {"train": 0, "val": 0, "test": 0, "unsplit": 0}
    seen_fingerprints: set[str] = set()
    duplicates = 0
    unlabelled = 0
    total = 0

    for idx, (src, remap, layout) in enumerate(zip(inputs, remaps, layouts)):
        for subset, img, label in _collect_yolo_entries(src):
            if label is None:
                unlabelled += 1
                continue
            fingerprint = _file_fingerprint(img)
            if fingerprint in seen_fingerprints:
                duplicates += 1
                continue
            seen_fingerprints.add(fingerprint)

            target_split = subset or ("train" if split_mode else "unsplit")
            if split_mode:
                dest_images = output / target_split / "images"
                dest_labels = output / target_split / "labels"
            else:
                dest_images = output / "images"
                dest_labels = output / "labels"
            dest_images.mkdir(parents=True, exist_ok=True)
            dest_labels.mkdir(parents=True, exist_ok=True)

            out_img = _merge_copy_image(img, dest_images, prefix=f"s{idx}")
            remapped = _remap_label_file(label, remap, src)
            (dest_labels / f"{out_img.stem}.txt").write_text(remapped, encoding="utf-8")
            counts[target_split] += 1
            total += 1

    if total == 0:
        raise DatasetError("Merge produced no images (all inputs empty or unlabelled).")
    if split_mode and counts["train"] == 0:
        raise DatasetError("Merged dataset has no train/ images.")
    if split_mode and counts["val"] == 0:
        raise DatasetError(
            "Merged dataset has no validation/ images. Split the inputs first "
            "(prepare_dataset.py split) or provide inputs that already contain a val/ split."
        )

    output.mkdir(parents=True, exist_ok=True)
    _write_classes(output, class_names)

    next_step = ""
    if split_mode:
        test_dir = Path("test/images") if counts["test"] > 0 else None
        write_data_yaml(
            output / "dataset.yaml",
            train_dir=Path("train/images"),
            val_dir=Path("val/images"),
            test_dir=test_dir,
            class_names=class_names,
            path=output.resolve(),
        )
        next_step = f"Train with: python scripts/train_model.py --data {output / 'dataset.yaml'}"
    else:
        next_step = (
            f"All inputs were unsplit — output is flat. Next: "
            f"python scripts/prepare_dataset.py split {output} {output}_split --seed 42"
        )

    return {
        "inputs": [str(p) for p in inputs],
        "output": str(output),
        "layout": "split" if split_mode else "flat",
        "class_names": class_names,
        "counts": counts,
        "images": total,
        "duplicates_skipped": duplicates,
        "unlabelled_skipped": unlabelled,
        "next_step": next_step,
    }


def write_data_yaml(
    output: Path,
    train_dir: Path,
    val_dir: Path,
    test_dir: Path | None,
    class_names: list[str],
    path: Path | None = None,
) -> Path:
    """Write an Ultralytics-compatible ``dataset.yaml``."""
    lines = [f"path: {(path or output).as_posix()}", f"train: {train_dir.as_posix()}"]
    if test_dir is not None:
        lines.append(f"test: {test_dir.as_posix()}")
    lines.append(f"val: {val_dir.as_posix()}")
    lines.append("names:")
    for idx, name in enumerate(class_names):
        lines.append(f"  {idx}: {name}")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output


def class_count_table(report: InspectionReport) -> list[dict]:
    """Rows for a pandas DataFrame / pretty table."""
    return [{"class": k, "count": v} for k, v in report.class_counts.items()]
