# Bảo mật khi làm việc — lô lab250_c62afeb67fdb (r3007)

## 1. Ca USB: hết giờ, muốn chép lô về nhà làm tiếp
Không được. Lô bàn giao là tài sản công ty dù ảnh gốc COCO công khai: metadata job, người gán và hiện trạng QC của lô là thông tin nội bộ, và quy trình đã chốt là dữ liệu không rời hệ thống quản lý. Tự ý chép USB vừa vi phạm chính sách thiết bị removable, vừa tạo bản nhân không kiểm soát được hash. Việc về nhà nếu cần: xin phê duyệt access từ xa qua hệ thống chính thức có xác thực và log, hoặc đăng ký làm thêm tại công ty. Không dùng email cá nhân hay "nhờ người khác làm hộ" — dữ liệu vẫn rời hệ thống và mất trách nhiệm giải trình.

## 2. Năm việc: được hay không
1. **Mở job được giao trên máy công ty** — Được. Đúng phân quyền: job của ai người đó mở, mọi thao tác có log.
2. **Chụp màn hình gửi người quen xem** — Không. Ảnh lô chứa nhãn, tiến độ và metadata nội bộ; gửi ra ngoài là rò rỉ dữ liệu dự án dù người nhận không làm gì thêm.
3. **Chép lô ra USB** — Không (như mục 1): thiết bị removable không kiểm soát được mã hoá và mất dấu.
4. **Dán nhãn thật của dữ liệu dự án vào chatbot** — Không với dữ liệu thật của công ty. Lưu ý khác biệt: bài lab này ảnh COCO là dữ liệu công khai nên việc hỏi AI về chúng được phép và đã ghi trong `submission/prompts.md`; ngoài đời thì nội bộ là nội bộ.
5. **Đưa tài khoản CVAT cho đồng nghiệp cùng làm** — Không. Mỗi người một tài khoản để dòng nào trong review_log truy vết đúng người đã xem; dùng chung tài khoản phá vỡ nguyên tắc "ai gán, ai kiểm" của Day 10.

## 3. Ca khuôn mặt: thấy mặt người rõ trong lô, guideline yêu cầu làm mờ
Lô r3007 có ảnh mặt người nhìn rõ, ví dụ `000000001296` (segment person ~192.000 px, giữ mask id 6185598) và `000000016598`, `000000004395`. Nếu guideline dự án yêu cầu làm mờ khuôn mặt thì đây **không phải việc tự làm qua validator**: validator chỉ bắt lỗi cấu trúc/nhãn, còn làm mờ là yêu cầu xử lý PII. Người phát hiện phải báo người phụ trách dữ liệu (DPO/quản lý lô) và **giữ trạng thái Hold cho lô**: không tự làm mờ (mọi sửa đổi ảnh làm sai hash đã bàn giao và có thể phá ngữ cảnh nhãn), không tự xoá ảnh (xoá im lặng mất dấu vết, viết lineage). Ảnh COCO val2017 là ảnh công khai nên bài này giữ nguyên; quy trình trên áp dụng khi lô là dữ liệu thật.
