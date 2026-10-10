"""Dataset tooling: format detection, inspection, conversion, splits, YAML."""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from src.datasets.prepare import (
    DatasetError,
    convert_to_yolo,
    deterministic_split,
    detect_format,
    inspect_dataset,
    merge_yolo_datasets,
    write_data_yaml,
)


def _make_image(path: Path, size=(60, 40)) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    img = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    assert cv2.imwrite(str(path), img)


def _make_varied_image(path: Path, seed: int, size=(60, 40)) -> None:
    """Unique pixels per seed — so content fingerprints never collide."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    img = rng.integers(0, 255, (size[1], size[0], 3), dtype=np.uint8)
    assert cv2.imwrite(str(path), img)


@pytest.fixture()
def yolo_dataset(tmp_path: Path) -> Path:
    root = tmp_path / "yolo_ds"
    (root / "images").mkdir(parents=True)
    (root / "labels").mkdir(parents=True)
    for i in range(5):
        _make_image(root / "images" / f"img{i}.jpg")
        (root / "labels" / f"img{i}.txt").write_text(
            "0 0.5 0.5 0.2 0.3\n1 0.3 0.3 0.1 0.1\n", encoding="utf-8"
        )
    return root


@pytest.fixture()
def yolo_dataset_with_problems(tmp_path: Path) -> Path:
    root = tmp_path / "broken"
    (root / "images").mkdir(parents=True)
    (root / "labels").mkdir(parents=True)
    _make_image(root / "images" / "good.jpg")
    (root / "labels" / "good.txt").write_text("0 0.5 0.5 0.2 0.3\n", encoding="utf-8")
    # missing label
    _make_image(root / "images" / "nolabel.jpg")
    # corrupt image
    (root / "images" / "corrupt.jpg").write_bytes(b"not an image at all")
    (root / "labels" / "corrupt.txt").write_text("0 0.5 0.5 0.2 0.3\n", encoding="utf-8")
    # invalid label line
    _make_image(root / "images" / "badline.jpg")
    (root / "labels" / "badline.txt").write_text("0 0.5 0.5 0.2\n", encoding="utf-8")
    # orphan label
    (root / "labels" / "orphan.txt").write_text("0 0.1 0.1 0.1 0.1\n", encoding="utf-8")
    return root


@pytest.fixture()
def voc_dataset(tmp_path: Path) -> Path:
    root = tmp_path / "voc"
    (root / "Annotations").mkdir(parents=True)
    _make_image(root / "Images" / "sample.jpg")
    xml = """<?xml version="1.0"?>
<annotation>
  <filename>sample.jpg</filename>
  <size><width>60</width><height>40</height><depth>3</depth></size>
  <object>
    <name>cola</name>
    <bndbox><xmin>6</xmin><ymin>4</ymin><xmax>30</xmax><ymax>36</ymax></bndbox>
  </object>
  <object>
    <name>juice</name>
    <bndbox><xmin>30</xmin><ymin>8</ymin><xmax>54</xmax><ymax>36</ymax></bndbox>
  </object>
</annotation>
"""
    (root / "Annotations" / "sample.xml").write_text(xml, encoding="utf-8")
    return root


@pytest.fixture()
def coco_dataset(tmp_path: Path) -> Path:
    root = tmp_path / "coco"
    (root / "images").mkdir(parents=True)
    _make_image(root / "images" / "c0.jpg")
    data = {
        "images": [{"id": 1, "file_name": "c0.jpg", "width": 60, "height": 40}],
        "annotations": [
            {"id": 1, "image_id": 1, "category_id": 7, "bbox": [6, 4, 24, 32]},
            {"id": 2, "image_id": 1, "category_id": 7, "bbox": [30, 8, 24, 28]},
        ],
        "categories": [{"id": 7, "name": "bottle"}],
    }
    (root / "annotations.json").write_text(json.dumps(data), encoding="utf-8")
    return root


def test_detect_yolo(yolo_dataset):
    assert detect_format(yolo_dataset) == "yolo"


def test_detect_voc(voc_dataset):
    assert detect_format(voc_dataset) == "voc"


def test_detect_coco(coco_dataset):
    assert detect_format(coco_dataset) == "coco"


def test_detect_unsupported(tmp_path):
    root = tmp_path / "weird"
    root.mkdir()
    (root / "data.parquet").write_bytes(b"\x00\x01")
    assert detect_format(root) == "unsupported"


def test_detect_missing_directory(tmp_path):
    with pytest.raises(DatasetError):
        detect_format(tmp_path / "nope")


def test_inspect_clean_yolo(yolo_dataset):
    report = inspect_dataset(yolo_dataset)
    assert report.ok
    assert report.image_count == 5
    assert report.label_count == 5
    assert report.class_counts == {"0": 5, "1": 5}
    assert report.missing_labels == []
    assert report.invalid_label_lines == []


def test_inspect_detects_problems(yolo_dataset_with_problems):
    report = inspect_dataset(yolo_dataset_with_problems)
    assert not report.ok
    assert any("nolabel.jpg" in m for m in report.missing_labels)
    assert any("corrupt.jpg" in c for c in report.corrupt_images)
    assert any("badline" in line for line in report.invalid_label_lines)
    assert any("orphan" in o for o in report.orphan_labels)


def test_inspect_unsupported_reports_clearly(tmp_path):
    root = tmp_path / "unknown"
    root.mkdir()
    (root / "labels.json").write_text("{}", encoding="utf-8")
    report = inspect_dataset(root)
    assert report.detected_format == "unsupported"
    assert not report.ok
    assert any("Unsupported" in note for note in report.notes)


def test_convert_voc_to_yolo(voc_dataset, tmp_path):
    dst = tmp_path / "out_voc"
    summary = convert_to_yolo(voc_dataset, dst)
    assert summary["format"] == "voc"
    assert summary["images"] == 1
    label = dst / "labels" / "sample.txt"
    assert label.exists()
    lines = label.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    cls, cx, cy, w, h = lines[0].split()
    assert cls == "0"
    assert 0 < float(cx) < 1 and 0 < float(cy) < 1
    assert 0 < float(w) <= 1 and 0 < float(h) <= 1
    assert (dst / "classes.txt").read_text(encoding="utf-8").split() == ["cola", "juice"]


def test_convert_coco_to_yolo(coco_dataset, tmp_path):
    dst = tmp_path / "out_coco"
    summary = convert_to_yolo(coco_dataset, dst)
    assert summary["format"] == "coco"
    assert summary["images"] == 1
    lines = (dst / "labels" / "c0.txt").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    cls, cx, cy, w, h = lines[0].split()
    assert cls == "0"
    assert 0 < float(w) <= 1


def test_convert_unsupported_raises(tmp_path):
    root = tmp_path / "nope"
    root.mkdir()
    with pytest.raises(DatasetError) as exc:
        convert_to_yolo(root, tmp_path / "out")
    assert "Unsupported" in str(exc.value)


def test_split_is_reproducible_and_leakage_free(yolo_dataset, tmp_path):
    out1 = tmp_path / "split1"
    out2 = tmp_path / "split2"
    s1 = deterministic_split(yolo_dataset, out1, ratios=(0.6, 0.2, 0.2), seed=42)
    s2 = deterministic_split(yolo_dataset, out2, ratios=(0.6, 0.2, 0.2), seed=42)
    assert s1["counts"] == s2["counts"]

    def names(subset_root: Path) -> dict[str, set[str]]:
        result = {}
        for subset in ("train", "val", "test"):
            imgs = subset_root / subset / "images"
            result[subset] = {p.name for p in imgs.glob("*")} if imgs.exists() else set()
        return result

    n1 = names(out1)
    total = sum(len(v) for v in n1.values())
    assert total == 5
    # no image appears in more than one subset
    assert not (n1["train"] & n1["val"])
    assert not (n1["train"] & n1["test"])
    assert not (n1["val"] & n1["test"])


def test_split_rejects_bad_ratios(yolo_dataset, tmp_path):
    with pytest.raises(DatasetError):
        deterministic_split(yolo_dataset, tmp_path / "s", ratios=(0.5, 0.5, 0.5))


def test_write_data_yaml(tmp_path):
    out = write_data_yaml(
        tmp_path / "data.yaml",
        train_dir=Path("train/images"),
        val_dir=Path("val/images"),
        test_dir=Path("test/images"),
        class_names=["cola", "juice"],
    )
    text = out.read_text(encoding="utf-8")
    assert "train: train/images" in text
    assert "val: val/images" in text
    assert "0: cola" in text
    assert "1: juice" in text


# --------------------------------------------------------------------------- merge
def _flat_dataset(root: Path, names: list[str], labels: dict[str, str], seed_base: int = 0) -> Path:
    (root / "images").mkdir(parents=True, exist_ok=True)
    (root / "labels").mkdir(parents=True, exist_ok=True)
    (root / "classes.txt").write_text("\n".join(names) + "\n", encoding="utf-8")
    for i, (fname, label) in enumerate(labels.items()):
        _make_varied_image(root / "images" / fname, seed=seed_base + i)
        (root / "labels" / Path(fname).stem).with_suffix(".txt").write_text(
            label, encoding="utf-8"
        )
    return root


def test_merge_flat_datasets_remaps_classes(tmp_path):
    a = _flat_dataset(tmp_path / "a", ["cola"], {"a0.jpg": "0 0.5 0.5 0.2 0.3\n"})
    b = _flat_dataset(
        tmp_path / "b", ["juice"], {"b0.jpg": "0 0.4 0.4 0.1 0.1\n"}, seed_base=100
    )
    out = tmp_path / "merged"
    summary = merge_yolo_datasets([a, b], out)

    assert summary["layout"] == "flat"
    assert summary["class_names"] == ["cola", "juice"]
    assert summary["counts"]["unsplit"] == 2
    assert summary["duplicates_skipped"] == 0
    assert (out / "classes.txt").read_text(encoding="utf-8").splitlines() == [
        "cola",
        "juice",
    ]
    # second input's class 0 ("juice") must be remapped to 1
    assert (out / "labels" / "b0.txt").read_text(encoding="utf-8").startswith("1 ")
    assert (out / "labels" / "a0.txt").read_text(encoding="utf-8").startswith("0 ")
    assert "split" in summary["next_step"]


def test_merge_removes_cross_source_duplicates(tmp_path):
    a = _flat_dataset(tmp_path / "a", ["cola"], {"shared.jpg": "0 0.5 0.5 0.2 0.3\n"})
    # identical bytes in the second input (same file copied over)
    b = tmp_path / "b"
    (b / "images").mkdir(parents=True)
    (b / "labels").mkdir(parents=True)
    (b / "classes.txt").write_text("cola\n", encoding="utf-8")
    shutil.copy2(a / "images" / "shared.jpg", b / "images" / "shared.jpg")
    shutil.copy2(a / "labels" / "shared.txt", b / "labels" / "shared.txt")

    summary = merge_yolo_datasets([a, b], tmp_path / "merged")
    assert summary["images"] == 1
    assert summary["duplicates_skipped"] == 1


def test_merge_skips_unlabelled_images(tmp_path):
    a = _flat_dataset(tmp_path / "a", ["cola"], {"a0.jpg": "0 0.5 0.5 0.2 0.3\n"})
    b = tmp_path / "b"
    _make_varied_image(b / "images" / "noLabel.jpg", seed=7)
    (b / "classes.txt").write_text("cola\n", encoding="utf-8")
    summary = merge_yolo_datasets([a, b], tmp_path / "merged")
    assert summary["unlabelled_skipped"] == 1
    assert summary["images"] == 1


def test_merge_requires_class_names(tmp_path):
    a = _flat_dataset(tmp_path / "a", ["cola"], {"a0.jpg": "0 0.5 0.5 0.2 0.3\n"})
    b = tmp_path / "b"
    _make_varied_image(b / "images" / "b0.jpg", seed=9)
    (b / "labels").mkdir(parents=True, exist_ok=True)
    (b / "labels" / "b0.txt").write_text("0 0.5 0.5 0.2 0.3\n", encoding="utf-8")
    with pytest.raises(DatasetError) as exc:
        merge_yolo_datasets([a, b], tmp_path / "merged")
    assert "no class names" in str(exc.value)


def test_merge_rejects_undefined_class_id(tmp_path):
    a = _flat_dataset(tmp_path / "a", ["cola"], {"a0.jpg": "0 0.5 0.5 0.2 0.3\n"})
    b = _flat_dataset(
        tmp_path / "b", ["juice"], {"b0.jpg": "5 0.4 0.4 0.1 0.1\n"}, seed_base=100
    )
    with pytest.raises(DatasetError) as exc:
        merge_yolo_datasets([a, b], tmp_path / "merged")
    assert "class id 5" in str(exc.value)


def test_merge_split_layout_preserves_splits_and_writes_yaml(tmp_path):
    # input A: split layout (3 train + 1 val)
    a = tmp_path / "a"
    (a / "classes.txt").write_text("cola\n", encoding="utf-8")
    for i in range(3):
        _make_varied_image(a / "train" / "images" / f"a{i}.jpg", seed=i)
        (a / "train" / "labels" / f"a{i}.txt").write_text(
            "0 0.5 0.5 0.2 0.3\n", encoding="utf-8"
        )
    _make_varied_image(a / "val" / "images" / "av0.jpg", seed=50)
    (a / "val" / "labels" / "av0.txt").write_text("0 0.5 0.5 0.2 0.3\n", encoding="utf-8")
    # input B: flat layout (1 unsplit image → goes to train/)
    b = _flat_dataset(
        tmp_path / "b", ["juice"], {"b0.jpg": "0 0.4 0.4 0.1 0.1\n"}, seed_base=100
    )

    out = tmp_path / "merged"
    summary = merge_yolo_datasets([a, b], out)

    assert summary["layout"] == "split"
    assert summary["counts"]["train"] == 4
    assert summary["counts"]["val"] == 1
    assert (out / "train" / "images" / "b0.jpg").exists()
    assert (out / "labels").is_dir() or (out / "train" / "labels").is_dir()
    assert (out / "train" / "labels" / "b0.txt").read_text(encoding="utf-8").startswith(
        "1 "
    )
    yaml_text = (out / "dataset.yaml").read_text(encoding="utf-8")
    assert "train: train/images" in yaml_text
    assert "val: val/images" in yaml_text
    assert "0: cola" in yaml_text and "1: juice" in yaml_text
    assert "train_model" in summary["next_step"]


def test_merge_split_layout_without_val_raises(tmp_path):
    a = tmp_path / "a"
    (a / "classes.txt").write_text("cola\n", encoding="utf-8")
    _make_varied_image(a / "train" / "images" / "a0.jpg", seed=1)
    (a / "train" / "labels" / "a0.txt").write_text("0 0.5 0.5 0.2 0.3\n", encoding="utf-8")
    b = _flat_dataset(
        tmp_path / "b", ["juice"], {"b0.jpg": "0 0.4 0.4 0.1 0.1\n"}, seed_base=100
    )
    with pytest.raises(DatasetError) as exc:
        merge_yolo_datasets([a, b], tmp_path / "merged")
    assert "no validation" in str(exc.value)


def test_merge_rejects_nonempty_output(tmp_path):
    a = _flat_dataset(tmp_path / "a", ["cola"], {"a0.jpg": "0 0.5 0.5 0.2 0.3\n"})
    b = _flat_dataset(
        tmp_path / "b", ["juice"], {"b0.jpg": "0 0.4 0.4 0.1 0.1\n"}, seed_base=100
    )
    out = tmp_path / "merged"
    out.mkdir()
    (out / "leftover.txt").write_text("x", encoding="utf-8")
    with pytest.raises(DatasetError) as exc:
        merge_yolo_datasets([a, b], out)
    assert "not empty" in str(exc.value)


def test_merge_yaml_class_names_via_dataset_yaml(tmp_path):
    a = _flat_dataset(tmp_path / "a", ["cola"], {"a0.jpg": "0 0.5 0.5 0.2 0.3\n"})
    (a / "classes.txt").unlink()  # force the yaml path
    (a / "dataset.yaml").write_text(
        "path: .\ntrain: train/images\nval: val/images\nnames:\n  0: cola\n",
        encoding="utf-8",
    )
    b = _flat_dataset(
        tmp_path / "b", ["juice"], {"b0.jpg": "0 0.4 0.4 0.1 0.1\n"}, seed_base=100
    )
    summary = merge_yolo_datasets([a, b], tmp_path / "merged")
    assert summary["class_names"] == ["cola", "juice"]
