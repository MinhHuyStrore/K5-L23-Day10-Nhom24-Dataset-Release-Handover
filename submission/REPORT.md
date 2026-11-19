# Báo cáo nhóm 24

## 1. Số liệu luyện tập
- F1 theo seed (`score_findings.py`, chế độ tự đo — chỉ F1 làm tròn, không dò từng ảnh):
  | Lô | lỗi luật | lỗi gán nhãn | tổng | truy vết |
  |---|---|---|---|---|
  | r3007 (seed luyện tập) | ≈ 1.0 | — (đang chờ cả nhóm xem ảnh) | ≈ 0.7 | tier_a/tier_b/notify ≈ 1.0 |
  | r3013 (thêm, qua `inject_release.py`) | ≈ 1.0 | — | ≈ 0.7 | — |
  | `runs/clean` (seed 5, `--no-faults`, 50 ảnh pool calib) | **0 lỗi báo** | 0 ứng viên | — | — |
- Số ứng viên trên lô sạch: **0** (50 ảnh). Hàng đợi trên r3007: **6 ảnh** (4 class_swap, 1 instance_merge, 1 missing_box) — đã render vào `runs/r3007/review/`, phân cho từng người ở [docs/REVIEW.md](../docs/REVIEW.md); verdict thật do người xem ảnh ghi, chưa chốt trước hạn.
- Ngưỡng đã chọn và cách chọn (không dùng `_private`):
  - `wrong_hash`: tự tính sha256 trên **bytes** (`rb`) của image + label + mask rồi so manifest — không kiểm định dạng 64 ký tự (lỗi gài chính là hash *hợp lệ của ảnh khác*).
  - `duplicate_box`: theo định nghĩa lỗi — cùng lớp, **cùng kích thước** (±2 px), lệch tâm ≤3 px; **không dùng IoU** vì GUIDE/DELIVERY nêu COCO có cặp tự nhiên chồng tới IoU ≈ 0.66 nhưng khác kích thước.
  - `bbox_out_of_bounds`: chỉ dung sai làm tròn 0,05 % (nhãn ghi 6 chữ số), bắt cả box tràn mép một chút.
  - `thing_overlap`: đếm pixel theo id segment trong mask (bỏ id 0); báo khi `area − pixel_thật > max(16 px, 5 %·area)`.
  - Ứng viên gán nhãn dựa **pixel mask** thay vì chỉ IoU bbox (gợi ý GUIDE Pha 2): khác lớp + trùng vị trí (IoU ≥ 0.4) → swap; ≥22 % pixel segment ngoài box cùng lớp → drift; segment ≥1000 px và ≥0,4 % ảnh không box nào → missing_box; một segment phủ pixel của 2 box **tách rời** (IoU box–box < 0.15, mỗi box giữ ≥20 % pixel) → instance_merge.
  - Diễn biến chỉnh ngưỡng: bản đầu dùng ghép IoU bbox lỏng sinh **23** ứng viên trên r3007 (phần lớn là box lồng nhau tự nhiên của COCO — chính GUIDE cảnh báo "ghép thô ra nhiều ứng viên"); siết sang tiêu chí pixel + cách biệt box làm hàng đợi r3007 còn **6** mà lô sạch vẫn **0** — số ứng viên lô sạch là thước nhiễu tự nhiên, dùng nó (không phải điểm) để chọn ngưỡng. Hàng đợi 6 ảnh xem hết trong phần việc Pha 2 của 5 người.

## 2. Vì sao báo hết ứng viên làm F1 giảm?
Đơn vị chấm là cặp `(type, target)` và **F1 phạt FP y như FN** (precision = TP/(TP+FP)). Ứng viên chỉ là *nghi vấn*: COCO vốn lệch tự nhiên giữa detection và panoptic (vật bị che, crowd, void), nên một phần hàng đợi không phải lỗi gán nhãn. Báo hết 23 ứng viên của bản validator đầu = thêm hàng chục cặp FP trong khi mỗi loại lỗi gài chỉ 0–3 cặp → precision tụt mạnh, recall gần như không tăng thêm (lỗi gán nhãn thật vốn đã nằm trong hàng đợi). Trên lô sạch điều này cực đoan: **0 lỗi gài nhưng vẫn có ứng viên** — nộp cả đống ứng viên thì F1 nhóm cross-check = 0 dù validator "bắt nhiều". Xem ảnh chính là bước lọc FP→TP; vì thế `review_log.csv` bắt buộc mọi dòng `confirmed` có ghi chú thấy gì.

## 3. Quyết định và lineage
- QC v1 = 11 đơn vị lỗi / 250 ảnh = **4,4 % > 2 %** (mỗi ảnh 1 lỗi; `scene_leak` tính **một cảnh** — `scene_214`) ⇒ **HOLD** theo ngưỡng Day 7: `decision HOLD` cho `lab250_c62afeb67fdb` trong `runs/lineage.jsonl`.
- `lineage.py impact` → `R-021: affected=True action=review_or_retrain`. Đổi dataset **không tự sửa model** đã học trên nhãn sai/hash sai/split rò ⇒ run R-021 phải rà lại hoặc train lại.
- v2 (`lab250_c62afeb67fdb_v2`, parent v1, đã `pack_release.py` + event `release`): **246 ảnh, 1675 nhãn, 4 ảnh rework, 2 ảnh panoptic-only ở lại**; delivery v1 không bị sửa (H1 PASS — mọi sửa chữa nằm trong `handover/`).

## 4. Hash chứng minh gì, không chứng minh gì?
- **Chứng minh**: file trên đĩa khớp đúng bản đã niêm phong trong manifest — phát hiện thiếu file, nội dung bị tráo (ca thực tế: `image_sha256` của `000000006723`/`000000020247` là hash **của ảnh khác**, format hoàn toàn hợp lệ), nhãn/mask bị sửa sau đóng gói, hỏng do cắt/trốn. Vì ảnh là JPEG gốc COCO, mở được + đúng nội dung mà hash sai ⇒ kết luận manifest sai, ghi hash thật vào v2.
- **Không chứng minh**: nhãn đúng hay ảnh mô tả đúng vật — mọi lỗi gán nhãn (`class_swap`, `bbox_drift`, `missing_box`, `category_swap`, `instance_merge`) giữ nguyên byte nên hash **qua mặt được hoàn toàn**; vì vậy mới cần đối chiếu detection ↔ panoptic + xem ảnh. Hash cũng không chứng minh nguồn gốc/PII.

## 5. Truy vết
- Ticket: model bỏ sót `bottle` bị che/mép, báo `scene_197`, `scene_309`; changelog: **v1.3 đổi quy tắc `bottle`** ⇒ "job guideline cũ" = job mang **v1.2 trong jobs.csv** (không phải metadata ảnh). Tiêu chí "có lớp bị đổi quy tắc" = ≥1 **box detection** `bottle` (class id 39) trong `labels/`.
- Kết quả (`scripts/trace_query.py`, tool chuẩn bị sẵn cho đề ẩn): `tier_a` = 2 ảnh trong 2 cảnh được báo; `tier_b` = 4 ảnh cùng điều kiện chưa ai báo; `notify` = 5 mã người (A02, A04, A05, Q01, Q03) — annotator + reviewer của các job chứa ảnh hai tầng. Tự đo F1 truy vết ≈ 1.0 cả ba danh sách.
- Vì sao guideline theo **job**: chính lô này validator tìm ra 2 ca `guideline_mismatch` — field trong metadata ảnh có thể là lỗi; tin nó sẽ loại nhầm ảnh cần báo.

## 6. Bug hoặc điểm chưa rõ trong lab (đã/ sẽ báo giảng viên)
1. **`scripts/inject_release.py` + `run_lab.py` crash trên Windows mã hoá cp1252**: dòng `print(...)` cuối main có tiếng Việt (`KHÔNG đọc`) gây `UnicodeEncodeError` khi chạy `python` thường (mặc định ANSI codepage); `run_lab.py` spawn con **không nối đuôi `-X utf8`** nên cả chuỗi fail mặc dù toàn bộ delivery + truth đã ghi xong trước lệnh in. Chạy `python -X utf8 ...` trực tiếp thì OK. Đề xuất: `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` đầu script.
2. Cùng nguyên nhân, `tests/test_pipeline.py` (mồi subprocess không UTF-8) fail trên máy Windows — nhóm sửa **trong tests/** (được phép): thêm `-X utf8` + `encoding="utf-8"` khi gọi script; scripts/ giữ nguyên.
3. Repo đề đã đổi tên trên GitHub (`...-Dataset-Release-Handover` → `K5-L23-Day10-Nhom24-...`); nhóm đã `git remote set-url`, các bạn khác lưu ý cập nhật.
4. Chưa rõ: khi một cảnh `scene_leak`, đơn vị chấm là 1 (theo GUIDE) nhưng validator nên báo ảnh nào "sai" trong cảnh — nhóm xử lý theo split **đa số của cảnh** khi dựng `truyvet.csv` v2 (nếu cảnh 5 ảnh mà metadata đa số là train thì giữ train, đổi ảnh khác số ít).
