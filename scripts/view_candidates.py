#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Công cụ xem ứng viên Pha 2 — vẽ box detection + viền segment panoptic lên ảnh.

  python scripts/view_candidates.py --delivery runs/r3007/delivery \
      --candidates runs/r3007/candidates.json --dir runs/r3007/review --crop

Dùng Pillow (được phép cho CÔNG CỤ XEM — validator thì chỉ thư viện chuẩn).
Mỗi ứng viên sinh một PNG đã phóng to vùng quan tâm: box đỏ = detection, viền xanh lá =
segment panoptic được nêu. Nhóm mở từng ảnh, đối chiếu với note trong candidates.json,
rồi tự ghi verdict vào review_log.csv (RULES: AI/công cụ không thay người quyết định).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import pngutil  # noqa: E402

from PIL import Image, ImageDraw  # noqa: E402


def mask_outline(delivery: Path, name: str, seg_id: int, size):
    """Set các pixel biên của segment (pixel thuộc seg có hàng xóm không thuộc seg)."""
    w, h, pixels = pngutil.read_rgb(delivery / "masks" / f"{name}.png")
    stride = w * 3
    out = []
    for y in range(h):
        for x in range(w):
            i = y * stride + x * 3
            if (pixels[i] | (pixels[i + 1] << 8) | (pixels[i + 2] << 16)) != seg_id:
                continue
            edge = False
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if not (0 <= nx < w and 0 <= ny < h):
                    edge = True
                    break
                j = ny * stride + nx * 3
                if (pixels[j] | (pixels[j + 1] << 8) | (pixels[j + 2] << 16)) != seg_id:
                    edge = True
                    break
            if edge:
                out.append((x * size[0] / w, y * size[1] / h))
    return w, h, out


def draw_boxes(draw, scale, ox, oy, boxes, color, width=3):
    for (x, y, bw, bh) in boxes:
        x1, y1 = (x - ox) * scale, (y - oy) * scale
        draw.rectangle([x1, y1, x1 + bw * scale, y1 + bh * scale], outline=color, width=width)


def main() -> int:
    ap = argparse.ArgumentParser(description="Render ứng viên thành ảnh có box + viền segment")
    ap.add_argument("--delivery", required=True)
    ap.add_argument("--candidates", required=True)
    ap.add_argument("--dir", required=True)
    ap.add_argument("--crop", action="store_true", default=True)
    ap.add_argument("--pad", type=int, default=140, help="ệm quanh box khi cắt (px)")
    args = ap.parse_args()
    delivery = Path(args.delivery)
    cands = json.loads(Path(args.candidates).read_text(encoding="utf-8"))["candidates"]
    out = Path(args.dir)
    out.mkdir(parents=True, exist_ok=True)

    for c in cands:
        name = c["image"]
        img_path = delivery / "images" / f"{name}.jpg"
        if not img_path.is_file():
            continue
        im = Image.open(img_path).convert("RGB")
        W, H = im.size
        regions = [c["box"]] if c.get("box") else []
        regions += c.get("boxes", [])
        if args.crop and regions:
            x1 = max(0, min(r[0] for r in regions) - args.pad)
            y1 = max(0, min(r[1] for r in regions) - args.pad)
            x2 = min(W, max(r[0] + r[2] for r in regions) + args.pad)
            y2 = min(H, max(r[1] + r[3] for r in regions) + args.pad)
        else:
            x1, y1, x2, y2 = 0, 0, W, H
        crop = im.crop((x1, y1, x2, y2))
        scale = max(1, round(900 / max(crop.size)))  # phóng to ảnh nhỏ cho dễ nhìn
        view = crop.resize((crop.width * scale, crop.height * scale), Image.NEAREST)
        draw = ImageDraw.Draw(view)
        draw_boxes(draw, scale, x1, y1, regions, "red")
        if c.get("segment_id"):
            try:
                _, _, pts = mask_outline(delivery, name, c["segment_id"], (crop.width * scale, crop.height * scale))
            except (OSError, ValueError):
                pts = []
            for px, py in pts:
                draw.rectangle([px - x1 * scale - 1, py - y1 * scale - 1,
                                px - x1 * scale + 1, py - y1 * scale + 1], fill="lime")
        label = f"{c['type']}: {c.get('note', '')[:80]}"
        draw.rectangle([0, 0, view.width, 22], fill="black")
        draw.text((4, 4), label[:150], fill="yellow")
        dst = out / f"{name}__{c['type']}.png"
        view.save(dst)
        print("đã vẽ ->", dst)
    print(f"{len(cands)} ứng viên -> {out} (mở từng ảnh, ghi verdict vào review_log.csv)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
