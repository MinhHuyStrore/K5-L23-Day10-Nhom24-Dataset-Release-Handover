# -*- coding: utf-8 -*-
"""Test đơn vị cho validator (bất đồng của Dũ — Pha 1/2).

Dựng một delivery tổng hợp siêu nhỏ bằng pngutil (PNG chuẩn), gài từng loại lỗi luật,
chạy validator qua CLI và kiểm errors.json. Không cần data_source, không mạng.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import pngutil  # noqa: E402


def solid_png(path: Path, w: int, h: int, rgb: tuple[int, int, int]) -> None:
    pngutil.write_rgb(path, w, h, bytes(list(rgb) * (w * h)))


def two_segment_png(path: Path, w: int, h: int, ids: list[int], split_at: int) -> None:
    """Half seg0 nền, còn lại chia hai segment theo id (không cần nền cho test diện tích)."""
    row = b""
    for x in range(w):
        sid = 0 if x < split_at else (ids[0] if x < (w + split_at) // 2 else ids[1])
        row += bytes([sid & 255, (sid >> 8) & 255, (sid >> 16) & 255])
    pngutil.write_rgb(path, w, h, row * h)


def fake_jpg(payload: bytes = b"\xff\xd8\xff\xe0fake-jpeg\xff\xd9") -> bytes:
    return payload


class ValidatorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.d = self.tmp / "delivery"
        for sub in ("images", "labels", "masks"):
            (self.d / sub).mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def build_base(self):
        """2 ảnh của scene_X (job J01, v1.2) + 1 ảnh scene_Y: tất cả sạch."""
        names = ["img_a", "img_b", "img_c"]
        items, meta_rows = {}, []
        pan = {"categories": [{"id": 1, "name": "person", "isthing": 1},
                              {"id": 2, "name": "bicycle", "isthing": 1}],
               "images": [], "annotations": []}
        for i, n in enumerate(names):
            img, lbl, msk = (self.d / "images" / f"{n}.jpg", self.d / "labels" / f"{n}.txt",
                             self.d / "masks" / f"{n}.png")
            img.write_bytes(b"\xff\xd8" + n.encode() + b"\xff\xd9")
            lbl.write_text("0 0.35 0.5 0.4 0.4\n", encoding="utf-8")
            two_segment_png(msk, 64, 64, [1, 2], 8)  # seg 1: 28 col, seg 2: 36 col (64 hàng)
            items[n] = {"image": f"images/{n}.jpg", "label": f"labels/{n}.txt", "mask": f"masks/{n}.png",
                        "image_sha256": hashlib.sha256(img.read_bytes()).hexdigest(),
                        "label_sha256": hashlib.sha256(lbl.read_bytes()).hexdigest(),
                        "mask_sha256": hashlib.sha256(msk.read_bytes()).hexdigest()}
            pan["images"].append({"id": i, "file_name": f"{n}.jpg", "width": 64, "height": 64})
            pan["annotations"].append({
                "image_id": i, "file_name": f"{n}.jpg",
                "segments_info": [
                    {"id": 1, "category_id": 1, "area": 28 * 64, "bbox": [8, 0, 28, 64], "iscrowd": 0},
                    {"id": 2, "category_id": 2, "area": 28 * 64, "bbox": [36, 0, 28, 64], "iscrowd": 0}]})
            scene = "scene_X" if n in ("img_a", "img_b") else "scene_Y"
            meta_rows.append({"image": n, "scene_id": scene, "split": "train", "job_id": "J01",
                              "guideline_version": "v1.2"})
        (self.d / "manifest.json").write_text(json.dumps({"dataset": "t", "num_classes": 2, "items": items}), encoding="utf-8")
        (self.d / "metadata.json").write_text(json.dumps({"items": meta_rows}), encoding="utf-8")
        (self.d / "classes.txt").write_text("0 person\n1 bicycle\n", encoding="utf-8")
        (self.d / "panoptic.json").write_text(json.dumps(pan), encoding="utf-8")
        (self.d / "jobs.csv").write_text("job_id,annotator,reviewer,guideline\nJ01,A01,Q01,v1.2\n", encoding="utf-8")
        (self.d / "release.json").write_text(json.dumps({"release_id": "lab_t_0001"}), encoding="utf-8")
        (self.d / "guideline").mkdir(exist_ok=True)
        (self.d / "guideline" / "changelog.md").write_text("## v1.2\nban dau\n", encoding="utf-8")
        return items

    def run_validator(self, out: str, candidates: str | None = None):
        cmd = [sys.executable, "-X", "utf8", str(ROOT / "validator" / "validate.py"), str(self.d), "--out", out]
        if candidates:
            cmd += ["--candidates", candidates]
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(Path(out).read_text(encoding="utf-8"))["errors"]

    def set_hash(self, items, n, field, data: bytes):
        self.d.joinpath(items[n][field.split("_")[0]]).write_bytes(data)
        self.d.joinpath("manifest.json").write_text(
            json.dumps({"dataset": "t", "num_classes": 2, "items": items}), encoding="utf-8")

    # ----------------------------------------------------------------- ca sạch
    def test_clean_delivery_reports_nothing(self):
        items = self.build_base()
        self.assertEqual(self.run_validator(str(self.tmp / "e.json")), [])

    # ----------------------------------------------------------------- file luật
    def test_missing_image(self):
        items = self.build_base()
        (self.d / "images" / "img_c.jpg").unlink()
        self.assertIn({"type": "missing_image", "target": "img_c"}, self.run_validator(str(self.tmp / "e.json")))

    def test_wrong_hash_detected(self):
        items = self.build_base()
        (self.d / "images" / "img_a.jpg").write_bytes(fake_jpg() + b"extra")
        errs = self.run_validator(str(self.tmp / "e.json"))
        self.assertIn({"type": "wrong_hash", "target": "img_a"}, errs)

    def test_wrong_hash_mask_too(self):
        items = self.build_base()
        (self.d / "masks" / "img_b.png").write_bytes(self.d.joinpath("masks", "img_b.png").read_bytes() + b"\x00")
        errs = self.run_validator(str(self.tmp / "e.json"))
        self.assertIn({"type": "wrong_hash", "target": "img_b"}, errs)

    # ----------------------------------------------------------------- nhãn
    def test_invalid_class(self):
        self.build_base()
        (self.d / "labels" / "img_a.txt").write_text("9 0.5 0.5 0.4 0.4\n", encoding="utf-8")
        self.assertIn({"type": "invalid_class", "target": "img_a"}, self.run_validator(str(self.tmp / "e.json")))

    def test_bbox_out_of_bounds_small_over_only(self):
        self.build_base()
        (self.d / "labels" / "img_b.txt").write_text("0 0.85 0.5 0.4 0.4\n", encoding="utf-8")  # x2=1.05 → tràn 5%
        self.assertIn({"type": "bbox_out_of_bounds", "target": "img_b"}, self.run_validator(str(self.tmp / "e.json")))

    def test_duplicate_box_offset_2px(self):
        self.build_base()
        (self.d / "labels" / "img_c.txt").write_text(
            "0 0.5 0.5 0.4 0.4\n0 0.53125 0.5 0.4 0.4\n", encoding="utf-8")  # lệch 2px/64
        self.assertIn({"type": "duplicate_box", "target": "img_c"}, self.run_validator(str(self.tmp / "e.json")))

    def test_exact_duplicate_box(self):
        """Box lap trung khit van la loi, ke ca khi IoU bang 1."""
        items = self.build_base()
        label = self.d / items["img_a"]["label"]
        label.write_text("0 0.5 0.5 0.4 0.4\n" * 2, encoding="utf-8")
        items["img_a"]["label_sha256"] = hashlib.sha256(label.read_bytes()).hexdigest()
        (self.d / "manifest.json").write_text(
            json.dumps({"num_classes": 2, "items": items}), encoding="utf-8")
        self.assertEqual(self.run_validator(str(self.tmp / "e.json")),
                         [{"type": "duplicate_box", "target": "img_a"}])

    def test_natural_overlapping_boxes_not_duplicate(self):
        """Hai box COCO chồng tự nhiên (IoU ~0.6) nhưng KHÁC kích thước: không được báo."""
        self.build_base()
        (self.d / "labels" / "img_a.txt").write_text(
            "0 0.5 0.5 0.4 0.4\n0 0.52 0.52 0.28 0.30\n", encoding="utf-8")
        errs = self.run_validator(str(self.tmp / "e.json"))
        self.assertNotIn({"type": "duplicate_box", "target": "img_a"}, errs)

    # ----------------------------------------------------------------- metadata
    def test_scene_leak_targets_scene_id(self):
        items = self.build_base()
        meta = json.loads((self.d / "metadata.json").read_text(encoding="utf-8"))
        meta["items"][2]["split"] = "val"  # img_c khác split với img_a/img_b? không — cùng cảnh phải khác
        meta["items"][0]["split"] = "val"  # scene_X giờ có cả train lẫn val
        (self.d / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
        errs = self.run_validator(str(self.tmp / "e.json"))
        self.assertIn({"type": "scene_leak", "target": "scene_X"}, errs)

    def test_guideline_mismatch_vs_job(self):
        items = self.build_base()
        meta = json.loads((self.d / "metadata.json").read_text(encoding="utf-8"))
        meta["items"][1]["guideline_version"] = "v1.3"
        (self.d / "metadata.json").write_text(json.dumps(meta), encoding="utf-8")
        errs = self.run_validator(str(self.tmp / "e.json"))
        self.assertIn({"type": "guideline_mismatch", "target": "img_b"}, errs)

    # ----------------------------------------------------------------- panoptic
    def test_invalid_category_id(self):
        items = self.build_base()
        pan = json.loads((self.d / "panoptic.json").read_text(encoding="utf-8"))
        pan["annotations"][0]["segments_info"][0]["category_id"] = 77  # id trống
        (self.d / "panoptic.json").write_text(json.dumps(pan), encoding="utf-8")
        errs = self.run_validator(str(self.tmp / "e.json"))
        self.assertIn({"type": "invalid_category_id", "target": "img_a"}, errs)

    def test_thing_overlap_area_overstated(self):
        items = self.build_base()
        pan = json.loads((self.d / "panoptic.json").read_text(encoding="utf-8"))
        pan["annotations"][1]["segments_info"][1]["area"] += 700  # >5% area và >16 px
        (self.d / "panoptic.json").write_text(json.dumps(pan), encoding="utf-8")
        errs = self.run_validator(str(self.tmp / "e.json"))
        self.assertIn({"type": "thing_overlap", "target": "img_b"}, errs)

    # ----------------------------------------------------------------- CLI
    def test_candidates_file_shape(self):
        items = self.build_base()
        # segment 'bicycle' không có box (chỉ có box person) -> ứng viên missing_box
        cpath = self.tmp / "c.json"
        self.run_validator(str(self.tmp / "e.json"), str(cpath))
        cands = json.loads(cpath.read_text(encoding="utf-8"))["candidates"]
        self.assertTrue(all({"image", "type", "note"} <= set(c) for c in cands))


if __name__ == "__main__":
    unittest.main()
