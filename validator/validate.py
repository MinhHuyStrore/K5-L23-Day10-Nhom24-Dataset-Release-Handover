#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validator của nhóm — bắt lỗi luật (Pha 1) và sinh ứng viên đối chiếu (Pha 2).

Giao diện cố định (GUIDE.md):

    python validator/validate.py <thư_mục_delivery> --out <errors.json> [--candidates <candidates.json>]

- errors.json: chỉ lỗi luật (9 loại). Lỗi gán nhãn KHÔNG vào thẳng file này; validator ghi
  ứng viên ra candidates.json, nhóm xem ảnh chốt vào review_log.csv rồi gộp bằng merge_review.py.
- Chỉ đọc thư mục delivery được truyền vào; chỉ thư viện chuẩn + scripts/pngutil.py; không mạng.
- Không nhúng tên ảnh/id/đáp án của seed nào vào code.

Ngưỡng và lý do: xem submission/REPORT.md (mục "Ngưỡng validator").
Tóm tắt:
  * bbox_out_of_bounds: chỉ chừa dung sai làm tròn (nhãn ghi 6 chữ số).
  * duplicate_box: box lặp cùng lớp, CÙNG KÍCH THƯỚC, lệch tâm vài pixel — cặp tự nhiên
    trong COCO chồng tới IoU ~0.66 nhưng khác kích thước, nên không dùng IoU làm tiêu chí.
  * thing_overlap: so số pixel thật của segment trong mask với `area` khai trong panoptic.json;
    dung sai 5% vì mask là sự thật, area sai lệch chỉ do làm tròn.
  * Ứng viên gán nhãn dùng pixel của mask (không chỉ IoU bbox) như GUIDE Pha 2 gợi ý; segment
    quá nhỏ bị bỏ vì không thể xem bằng mắt; ngưỡng nhiễu đo trên lô sạch runs/clean.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import pngutil  # noqa: E402

# ------------------------------------------------------------------ ngưỡng
OUT_TOL = 5e-4            # bbox_out_of_bounds: dung sai làm tròn chuẩn hoá
DUP_SIZE_PX = 2.0         # duplicate_box: hai box lặp phải cùng kích thước (±2 px)
DUP_SHIFT_PX = 3.0        # duplicate_box: lệch tâm tối đa (lỗi gài 1–2 px, chừa cho ảnh resize)
OVERLAP_LOSS_FRAC = 0.05  # thing_overlap: dung sai so area
OVERLAP_LOSS_MIN = 16     # thing_overlap: bỏ mất mát dưới 16 px
SWAP_MIN_IOU = 0.4        # ứng viên class_swap/category_swap: trùng vị trí, khác lớp
PAIR_IOU_MIN = 0.1        # dưới ngưỡng này: box và segment coi như không liên quan
DRIFT_IOU_MAX = 0.78      # cặp cùng lớp IoU thấp hơn mức này mới xem tới khả năng drift
DRIFT_OUT_FRAC = 0.22     # ứng viên bbox_drift: >=22% pixel segment ngoài box cùng lớp
MERGE_BOX_IOU = 0.15      # ứng viên instance_merge: hai box phải tách rời (IoU < 0.15)
MIN_SEG_PX = 1000         # ứng viên: segment dưới 1000 px bỏ ngoài hàng đợi xem ảnh
MIN_SEG_FRAC = 0.004      #   và dưới 0.4% diện tích ảnh


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Rect:
    """Bbox toạ độ pixel (x1, y1, x2, y2)."""

    __slots__ = ("x1", "y1", "x2", "y2")

    def __init__(self, x1: float, y1: float, x2: float, y2: float):
        self.x1, self.y1, self.x2, self.y2 = x1, y1, x2, y2

    @property
    def area(self) -> float:
        return max(0.0, self.x2 - self.x1) * max(0.0, self.y2 - self.y1)

    @property
    def center(self) -> tuple[float, float]:
        return (self.x1 + self.x2) / 2.0, (self.y1 + self.y2) / 2.0

    def iou(self, o: "Rect") -> float:
        ix = max(0.0, min(self.x2, o.x2) - max(self.x1, o.x1))
        iy = max(0.0, min(self.y2, o.y2) - max(self.y1, o.y1))
        inter = ix * iy
        union = self.area + o.area - inter
        return inter / union if union > 0 else 0.0

    def contains(self, x: int, y: int) -> bool:
        return self.x1 <= x < self.x2 and self.y1 <= y < self.y2

    def as_list(self) -> list[int]:
        return [round(self.x1), round(self.y1), round(self.x2 - self.x1), round(self.y2 - self.y1)]


def _overlap_frac(a: Rect, b: Rect) -> float:
    """Tỉ lệ diện tích rect a nằm trong rect b."""
    ix = max(0.0, min(a.x2, b.x2) - max(a.x1, b.x1))
    iy = max(0.0, min(a.y2, b.y2) - max(a.y1, b.y1))
    return (ix * iy) / a.area if a.area > 0 else 0.0


def pixel_counts(pixels: bytearray) -> dict[int, int]:
    """Số pixel thật của từng id segment trong mask (id = R + G*256 + B*65536, bỏ nền 0)."""
    counts: dict[int, int] = defaultdict(int)
    for r, g, b in zip(pixels[0::3], pixels[1::3], pixels[2::3]):
        if r or g or b:
            counts[r | (g << 8) | (b << 16)] += 1
    return dict(counts)


def seg_pixels_in_rects(d: "Delivery", name: str, seg_id: int, rects: list[Rect]) -> tuple[int, list[int]]:
    """Một lượt duyệt mask: tổng số pixel của seg_id và số rơi vào từng rect quan tâm."""
    width, height, pixels = d.mask(name)
    stride = width * 3
    hits = [0] * len(rects)
    total = 0
    for y in range(height):
        row = pixels[y * stride:(y + 1) * stride]
        for x, (r, g, b) in enumerate(zip(row[0::3], row[1::3], row[2::3])):
            if (r | (g << 8) | (b << 16)) == seg_id:
                total += 1
                for i, rect in enumerate(rects):
                    if rect.contains(x, y):
                        hits[i] += 1
    return total, hits


# ------------------------------------------------------------------ lô delivery
class Delivery:
    """Đọc delivery, cache mask để không giải mã PNG hai lần."""

    def __init__(self, root: Path):
        self.root = root
        self.manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        self.metadata = json.loads((root / "metadata.json").read_text(encoding="utf-8"))
        with open(root / "jobs.csv", newline="", encoding="utf-8-sig") as f:
            self.jobs = {row["job_id"].strip(): row for row in csv.DictReader(f)}
        self.num_classes = int(self.manifest.get("num_classes", 80))
        self.class_by_id: dict[int, str] = {}
        for line in (root / "classes.txt").read_text(encoding="utf-8").splitlines():
            parts = line.strip().split(" ", 1)
            if len(parts) == 2 and parts[0].lstrip("-").isdigit():
                self.class_by_id[int(parts[0])] = parts[1]
        self.pan = json.loads((root / "panoptic.json").read_text(encoding="utf-8"))
        self.cat_by_id = {c["id"]: c for c in self.pan["categories"]}
        self.thing_ids = {c["id"] for c in self.pan["categories"] if c.get("isthing")}
        self.name_by_cat = {c["id"]: c["name"] for c in self.pan["categories"]}
        self.size_by_name: dict[str, tuple[int, int]] = {}
        for img in self.pan.get("images", []):
            stem = Path(img.get("file_name", "")).stem
            if stem and img.get("width") and img.get("height"):
                self.size_by_name[stem] = (int(img["width"]), int(img["height"]))
        self.ann_by_name = {Path(a["file_name"]).stem: a for a in self.pan.get("annotations", [])}
        self.items: dict[str, dict] = dict(self.manifest.get("items", {}))
        self._mask_cache: dict[str, tuple[int, int, bytearray]] = {}
        self._counts_cache: dict[str, dict[int, int]] = {}

    def path(self, name: str, key: str) -> Path:
        return self.root / self.items[name][key]

    def size(self, name: str) -> tuple[int, int]:
        """(width, height) ưu tiên panoptic.json, rồi header JPEG (ảnh vẫn mở được), rồi kích thước mask."""
        if name in self.size_by_name:
            return self.size_by_name[name]
        parsed = parse_jpeg_size(self.path(name, "image"))
        if parsed:
            return parsed
        w, h, _ = self.mask(name)
        return (w, h)

    def mask(self, name: str) -> tuple[int, int, bytearray]:
        if name not in self._mask_cache:
            self._mask_cache[name] = pngutil.read_rgb(self.path(name, "mask"))
        return self._mask_cache[name]

    def counts(self, name: str) -> dict[int, int]:
        if name not in self._counts_cache:
            self._counts_cache[name] = pixel_counts(self.mask(name)[2])
        return self._counts_cache[name]

    def boxes(self, name: str) -> list[dict]:
        """Boxes từ label YOLO: class id + tên + Rect pixel."""
        path = self.path(name, "label")
        if not path.is_file():
            return []
        width, height = self.size(name)
        out = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            parts = line.split()
            if len(parts) < 5 or not parts[0].lstrip("-").isdigit():
                continue
            try:
                cx, cy, w, h = map(float, parts[1:5])
            except ValueError:
                continue
            cid = int(parts[0])
            out.append({"id": cid, "cls": self.class_by_id.get(cid, f"class_{cid}"),
                        "rect": Rect((cx - w / 2) * width, (cy - h / 2) * height,
                                     (cx + w / 2) * width, (cy + h / 2) * height)})
        return out

    def thing_segments(self, name: str) -> list[dict]:
        """Thing segments không iscrowd, có pixel thật trong mask, gắn Rect + tên lớp."""
        ann = self.ann_by_name.get(name)
        if not ann:
            return []
        counts = self.counts(name)
        out = []
        for s in ann.get("segments_info", []):
            if s.get("iscrowd") or s.get("category_id") not in self.thing_ids:
                continue
            real = counts.get(s.get("id"), 0)
            if real <= 0:
                continue
            x, y, w, h = s["bbox"]
            out.append({"id": s["id"], "category_id": s["category_id"],
                        "name": self.name_by_cat.get(s["category_id"], "?"),
                        "area": int(s.get("area", 0)), "real": real,
                        "rect": Rect(x, y, x + w, y + h)})
        return out


def parse_jpeg_size(path: Path) -> tuple[int, int] | None:
    """(width, height) từ marker SOF, chỉ dùng bytes."""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if not data.startswith(b"\xff\xd8"):
        return None
    pos, n = 2, len(data)
    while pos + 4 <= n:
        if data[pos] != 0xFF:
            pos += 1
            continue
        marker = data[pos + 1]
        if marker in (0x01, 0xD8) or 0xD0 <= marker <= 0xD7:
            pos += 2
            continue
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            if pos + 9 <= n:
                h = int.from_bytes(data[pos + 5:pos + 7], "big")
                w = int.from_bytes(data[pos + 7:pos + 9], "big")
                return (w, h) if w and h else None
            return None
        seg_len = int.from_bytes(data[pos + 2:pos + 4], "big")
        pos += 2 + max(2, seg_len)
    return None


# ------------------------------------------------------------------ Pha 1: lỗi luật
def rule_errors(d: Delivery) -> tuple[list[dict], set[str]]:
    errors: list[dict] = []
    seen: set[tuple[str, str]] = set()
    faulty: set[str] = set()

    def add(kind: str, target: str):
        if (kind, target) not in seen:
            seen.add((kind, target))
            errors.append({"type": kind, "target": target})

    valid_classes = set(range(d.num_classes))
    for name in sorted(d.items):
        item = d.items[name]
        img = d.path(name, "image")
        lbl = d.path(name, "label")
        msk = d.path(name, "mask")

        if not img.is_file():
            add("missing_image", name)
            faulty.add(name)
            continue

        if any(sha256_of(p) != item[k] for k, p in
               (("image_sha256", img), ("label_sha256", lbl), ("mask_sha256", msk))
               if item.get(k) and p.is_file()):
            add("wrong_hash", name)
            faulty.add(name)

        boxes = d.boxes(name)
        if any(b["id"] not in valid_classes for b in boxes):
            add("invalid_class", name)
            faulty.add(name)

        width, height = d.size(name)
        if any(b["rect"].x1 < -OUT_TOL * width or b["rect"].y1 < -OUT_TOL * height
               or b["rect"].x2 > width * (1 + OUT_TOL) or b["rect"].y2 > height * (1 + OUT_TOL)
               for b in boxes):
            add("bbox_out_of_bounds", name)
            faulty.add(name)

        dup = False
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                a, b = boxes[i], boxes[j]
                if a["id"] != b["id"]:
                    continue
                aw, ah = a["rect"].x2 - a["rect"].x1, a["rect"].y2 - a["rect"].y1
                bw, bh = b["rect"].x2 - b["rect"].x1, b["rect"].y2 - b["rect"].y1
                if (abs(aw - bw) <= DUP_SIZE_PX and abs(ah - bh) <= DUP_SIZE_PX
                        and abs(a["rect"].center[0] - b["rect"].center[0]) <= DUP_SHIFT_PX
                        and abs(a["rect"].center[1] - b["rect"].center[1]) <= DUP_SHIFT_PX):
                    dup = True
        if dup:
            add("duplicate_box", name)
            faulty.add(name)

    for name in sorted(d.items):
        if name in faulty:
            continue  # mỗi ảnh mang nhiều nhất một lỗi: hết nguồn lỗi panoptic
        ann = d.ann_by_name.get(name)
        if not ann:
            continue
        counts = d.counts(name)  # decode mask để kiểm area + category
        for s in ann.get("segments_info", []):
            if s.get("category_id") not in d.cat_by_id:
                add("invalid_category_id", name)
                faulty.add(name)
            area = int(s.get("area", 0))
            real = counts.get(s.get("id"), 0)
            if real > 0 and area - real > max(OVERLAP_LOSS_MIN, OVERLAP_LOSS_FRAC * area):
                add("thing_overlap", name)
                faulty.add(name)

    splits_by_scene: dict[str, set[str]] = defaultdict(set)
    for m in d.metadata.get("items", []):
        splits_by_scene[m["scene_id"]].add(m["split"])
    for scene, splits in sorted(splits_by_scene.items()):
        if len(splits) > 1:
            add("scene_leak", scene)  # target là scene_id, đơn vị tính một cảnh
            for m in d.metadata["items"]:
                if m["scene_id"] == scene:
                    faulty.add(m["image"])

    for m in d.metadata.get("items", []):
        job = d.jobs.get(m["job_id"])
        if job and m.get("guideline_version") != job.get("guideline", "").strip():
            add("guideline_mismatch", m["image"])
            faulty.add(m["image"])

    return sorted(errors, key=lambda e: (e["type"], e["target"])), faulty


# ------------------------------------------------------------------ Pha 2: ứng viên
def candidates(d: Delivery, faulty: set[str]) -> list[dict]:
    out: list[dict] = []
    for name in sorted(d.items):
        if name in faulty:
            continue  # ảnh đã có lỗi luật: xử lý luật trước, khỏi trùng hàng đợi
        boxes = d.boxes(name)
        segs = d.thing_segments(name)
        if not segs:
            continue
        width, height = d.size(name)

        def iou(b, s):
            return s["rect"].iou(b["rect"])

        # 1) Trùng vị trí, khác lớp -> class_swap hoặc category_swap (xem ảnh mới chốt được)
        matched_seg: set[int] = set()
        matched_box: set[int] = set()
        for s in segs:
            partner = max(boxes, key=lambda b: iou(b, s), default=None)
            best_iou = iou(partner, s) if partner else 0.0
            same_partner = max((b for b in boxes if b["cls"] == s["name"]), key=lambda b: iou(b, s), default=None)
            same_iou = iou(same_partner, s) if same_partner else 0.0
            if (partner and partner["cls"] != s["name"] and best_iou >= SWAP_MIN_IOU
                    and best_iou >= same_iou):
                out.append({"image": name, "type": "class_swap", "alt_type": "category_swap",
                            "note": f"box '{partner['cls']}' và segment '{s['name']}' trùng vị trí "
                                    f"(IoU {best_iou:.2f}) — mở ảnh xem bên nào sai",
                            "det_class": partner["cls"], "pan_class": s["name"],
                            "iou": round(best_iou, 3), "box": partner["rect"].as_list(),
                            "segment_id": s["id"]})
                matched_seg.add(id(s))
                matched_box.add(id(partner))

        # 2) Segment phủ HAI box CÁCH BIỆT nhau -> instance_merge. Khi gộp hai vật, bbox của
        #    segment giữ rất rộng so với từng box, nên đo tỉ lệ box nằm trong bbox segment
        #    (không dùng IoU); pixel-based: mỗi box phải giữ một phần pixel đáng kể của segment.
        for s in segs:
            if s["real"] < MIN_SEG_PX or id(s) in matched_seg:
                continue
            near = [b for b in boxes if b["cls"] == s["name"]
                    and _overlap_frac(b["rect"], s["rect"]) >= 0.6]
            if len(near) < 2:
                continue
            total, hits = seg_pixels_in_rects(d, name, s["id"], [b["rect"] for b in near])
            if not total:
                continue
            scored = sorted((h / total for h in hits), reverse=True)
            fa, fb = scored[0], scored[1]
            # phải có ít nhất một cặp box CÁCH BIỆT nhau trong số hai box ăn pixel nhiều nhất
            top2 = [b for _, b in sorted(zip(hits, near), key=lambda hb: -hb[0])]
            if top2[0]["rect"].iou(top2[1]["rect"]) >= MERGE_BOX_IOU:
                continue
            if fb >= 0.2 and fa + fb <= 1.4:
                out.append({"image": name, "type": "instance_merge",
                            "note": f"segment '{s['name']}' (id {s['id']}) phủ pixel của 2 box tách rời cùng lớp "
                                    f"({fa:.0%} + {fb:.0%}) — kiểm tra ảnh: hai vật bị gộp thành một segment",
                            "det_class": s["name"], "boxes": [b["rect"].as_list() for b in top2[:2]],
                            "segment_id": s["id"]})
                matched_seg.add(id(s))

        # 3) Ghép tham lam cùng lớp theo IoU giảm dần; drift = pixel segment ngoài box
        pairs = sorted(({ "s": s, "b": b, "iou": iou(b, s)}
                        for s in segs for b in boxes if s["name"] == b["cls"]),
                       key=lambda p: -p["iou"])
        for p in pairs:
            if p["iou"] < PAIR_IOU_MIN or id(p["s"]) in matched_seg or id(p["b"]) in matched_box:
                continue
            matched_seg.add(id(p["s"]))
            matched_box.add(id(p["b"]))
            if p["iou"] >= DRIFT_IOU_MAX or p["s"]["real"] < MIN_SEG_PX:
                continue
            total, hits = seg_pixels_in_rects(d, name, p["s"]["id"], [p["b"]["rect"]])
            out_frac = 1.0 - hits[0] / total if total else 0.0
            if out_frac >= DRIFT_OUT_FRAC:
                out.append({"image": name, "type": "bbox_drift",
                            "note": f"{out_frac:.0%} pixel segment '{p['s']['name']}' nằm ngoài box cùng lớp "
                                    f"(IoU {p['iou']:.2f})",
                            "det_class": p["b"]["cls"], "iou": round(p["iou"], 3),
                            "out_frac": round(out_frac, 3), "box": p["b"]["rect"].as_list(),
                            "segment_id": p["s"]["id"]})

        # 4) Segment thing lớn, rõ, không box nào -> missing_box (hoặc vật ngoài tầm nhìn det)
        for s in segs:
            if id(s) in matched_seg or s["real"] < MIN_SEG_PX or s["real"] < MIN_SEG_FRAC * width * height:
                continue
            if any(iou(b, s) >= PAIR_IOU_MIN for b in boxes):
                continue
            out.append({"image": name, "type": "missing_box",
                        "note": f"segment thing '{s['name']}' ({s['real']} px, bbox {s['rect'].as_list()}) "
                                "không có box detection nào gần",
                        "pan_class": s["name"], "segment_id": s["id"],
                        "box": s["rect"].as_list()})
    return out


# ------------------------------------------------------------------ main
def main() -> int:
    ap = argparse.ArgumentParser(description="Validator phát hành dataset — chỉ đọc delivery, chỉ thư viện chuẩn")
    ap.add_argument("delivery", help="thư mục delivery của lô")
    ap.add_argument("--out", required=True, help="ghi errors.json (chỉ lỗi luật)")
    ap.add_argument("--candidates", help="ghi candidates.json (ứng viên cần xem ảnh, Pha 2)")
    args = ap.parse_args()

    root = Path(args.delivery)
    if not (root / "manifest.json").is_file():
        raise SystemExit(f"{root} không phải thư mục delivery (thiếu manifest.json)")
    d = Delivery(root)

    errors, faulty = rule_errors(d)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"errors": errors}, indent=1) + "\n", encoding="utf-8")
    by_type: dict[str, int] = defaultdict(int)
    for e in errors:
        by_type[e["type"]] += 1
    print(f"{len(errors)} lỗi luật -> {args.out}")
    for t in sorted(by_type):
        print(f"  {t}: {by_type[t]}")

    if args.candidates:
        cands = candidates(d, faulty)
        cpath = Path(args.candidates)
        cpath.parent.mkdir(parents=True, exist_ok=True)
        cpath.write_text(json.dumps({"candidates": cands}, indent=1) + "\n", encoding="utf-8")
        ctype: dict[str, int] = defaultdict(int)
        for c in cands:
            ctype[c["type"]] += 1
        print(f"{len(cands)} ứng viên -> {args.candidates}")
        for t in sorted(ctype):
            print(f"  {t}: {ctype[t]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
