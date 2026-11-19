# Validator của nhóm

Viết `validate.py` ở đây. Giao diện cố định:

```
python validator/validate.py <thư_mục_delivery> --out <errors.json> [--candidates <candidates.json>]
```

Chỉ đọc thư mục delivery được truyền vào; chỉ thư viện chuẩn; không mạng. Xem [GUIDE.md](../GUIDE.md) Pha 1–2 và [RULES.md](../RULES.md).

## Cách nhóm đã dùng

```
python validator/validate.py runs/r3007/delivery --out runs/r3007/errors.json --candidates runs/r3007/candidates.json
```

- `errors.json`: chỉ lỗi luật (9 loại). Validator không đọc `_private/`, không dùng mạng, chỉ thư viện chuẩn + `scripts/pngutil.py`.
- `candidates.json`: ứng viên đối chiếu detection ↔ panoptic (dựa trên pixel mask, không chỉ IoU bbox). Nhóm xem ảnh từng ứng viên, ghi `review_log.csv`, rồi gộp:
  ```
  python scripts/merge_review.py --rules runs/r3007/errors.json --review runs/r3007/review_log.csv --out runs/r3007/errors.json
  ```
- Ngưỡng được chỉnh và đo trên lô sạch: `python scripts/inject_release.py --seed 5 --no-faults --out runs/clean` (lý do từng ngưỡng: `submission/prompts.md` và `REPORT.md`).
