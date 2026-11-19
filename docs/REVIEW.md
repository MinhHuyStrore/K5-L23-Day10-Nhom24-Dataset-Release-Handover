# Bảng review ứng viên — r3007 (Pha 2)

Nguồn: `runs/r3007/candidates.json` (validator `--candidates`). Ảnh đã vẽ sẵn box đỏ (detection)
+ viền xanh lá (segment panoptic) trong `runs/r3007/review/`. **Mỗi người mở ảnh gốc trong
`delivery/images/` để quyết — RULES: dòng `confirmed`/`rejected` là kết luận của người xem, ghi rõ ai xem.**

| # | Ảnh | Ứng viên | Tín hiệu validator | Người xem | Người đối chứng | Verdict |
|---|---|---|---|---|---|---|
| 1 | 000000009483 | class_swap ⇄ category_swap | box `laptop` vs segment `tv` trùng vị trí IoU 0.99 | Tùng | Dũ | pending |
| 2 | 000000019742 | class_swap ⇄ category_swap | box `vase` vs segment `baseball bat` IoU 0.99 | Dũ | Tùng | pending |
| 3 | 000000023272 | class_swap ⇄ category_swap | box `bus` vs segment `car` IoU 1.00 | Bỉn | Phạm | pending |
| 4 | 000000023781 | class_swap ⇄ category_swap | box `carrot` vs segment `motorcycle` IoU 0.99 | Phạm | Bỉn | pending |
| 5 | 000000013291 | instance_merge | segment `frisbee` (id 13419440) phủ 2 box `frisbee` tách rời, 63% + 37% pixel | Huy | Bỉn | pending |
| 6 | 000000007511 | missing_box | segment `person` 14.530 px, bbox [386,241,123,231], không box nào gần | Tùng | Phạm | pending |

Cách ghi — sửa `runs/r3007/review_log.csv` (giữ header), mỗi dòng verdict thay `pending`:

- `confirmed` = đúng lỗi gán nhãn; ghi chú ≥ 20 ký tự mô tả **thấy gì trong ảnh**, ví dụ
  "báo 23272: xe buýt hai tầng, panoptic ghi car, detection đúng ⇒ category_swap" — và nêu tên người xem.
- `rejected` = lệch tự nhiên (vật bị che một phần, crowd, hai vật sát nhau, void COCO); nêu lý do quan sát được.
- Với swap: nguồn nào khớp vật trong ảnh thì nguồn **kia** sai — chọn `class_swap` nếu detection sai, `category_swap` nếu panoptic sai. merge_review chỉ nhận đúng một trong hai type.
- Ảnh nhỏ (khoảng 240×320): mở `runs/r3007/review/*.png` (đã phóng to vùng quan tâm) rồi đối chiếu ảnh gốc.

Chốt review xong chạy lần lượt (Huy):

```
python -X utf8 scripts/merge_review.py --rules runs/r3007/errors.json --review runs/r3007/review_log.csv --out runs/r3007/errors.json
python -X utf8 scripts/build_v2.py --delivery runs/r3007/delivery --errors runs/r3007/errors.json --out runs/r3007/handover
python -X utf8 scripts/pack_release.py runs/r3007/handover/lab250_c62afeb67fdb_v2
python -X utf8 scripts/check_handover.py --run runs/r3007
python -X utf8 scripts/score_findings.py --run runs/r3007
python -X utf8 scripts/export_submission.py --run runs/r3007
```

(Lỗi confirmed thuộc detection → `build_v2.py` tự chuyển ảnh sang `rework_queue.csv`;
thuộc panoptic-only → ảnh ở lại v2, tự ghi vào Ghi chú README.txt.)
