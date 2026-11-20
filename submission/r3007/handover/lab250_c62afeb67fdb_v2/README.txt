Release: lab250_c62afeb67fdb_v2
Parent: lab250_c62afeb67fdb
Số ảnh: 244
Số nhãn: 1667
Guideline: v1.2: J01-J04; v1.3: J05-J10
QC v1: 14/250 = 5.6%
Kết luận v1: Hold — tỉ lệ lỗi 5.6% vượt ngưỡng 2% (Day 7); lỗi luật ở mức file, chốt từ validator
Kết luận v2: Rework — tách 6 ảnh lỗi detection sang rework_queue; sửa hash/guideline/split ngay trong v2; 3 ảnh lỗi panoptic ở lại, báo team panoptic

Ghi chú:
- wrong_hash (2 ảnh): đã mở/giải mã từng ảnh trước khi sửa — ảnh còn nguyên, chỉ manifest v1 sai; manifest.csv v2 ghi sha256 thật.
- guideline_mismatch: truyvet.csv lấy guideline theo jobs.csv của job (không theo metadata ảnh).
- scene_leak (scene_214): cả cảnh được đưa về split đa số của nó trong truyvet.csv.
- Ảnh lỗi chỉ ở panoptic (ở lại v2, KHÔNG vào rework): 000000013659 (thing_overlap), 000000022192 (thing_overlap), 000000023781 (category_swap). Chuyển kèm lô cho team panoptic xử lý masks.
- Ảnh rework giao lại đúng annotator/reviewer theo jobs.csv; chờ gán lại, không vào v2.
