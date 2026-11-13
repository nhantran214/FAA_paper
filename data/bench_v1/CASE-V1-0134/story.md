# Xử lý xuất hủy 30 thùng hàng hư hỏng tại kho hàng

Công ty TNHH Vận Tải và Logistics Minh Anh, một doanh nghiệp có 120 nhân viên và 5 kho hàng lớn ở TP.HCM và Hà Nội, chuyên về vận chuyển và lưu trữ hàng hóa tiêu dùng nhanh cho các đối tác bán lẻ, đã phát hiện 30 thùng hàng hóa bị ẩm mốc và hư hỏng vào ngày 20/05/2026. Mỗi thùng hàng có giá trị khoảng 1.500.000 đồng, tổng giá trị ước tính khoảng 45.000.000 đồng (trước thuế). Quy trình xử lý được kích hoạt để ghi giảm tài sản và yêu cầu phê duyệt xử lý hàng hư từ cấp quản lý.

## Diễn biến

1. **DP-01** kích hoạt quy trình với tiêu đề "Xử lý xuất hủy 30 thùng hàng hư hỏng tại kho hàng".
2. **THU-KHO** lập biên bản kiểm tra (BB-001) ghi nhận 30 thùng hàng hóa bị hư hỏng.
3. **DE-KH** lập phiếu kiểm kê (PK-001) với 30 thùng hàng hóa, đơn giá 1.500.000 đồng/thùng, thuế suất 10% (theo quy định VAT_10).
4. **DE-KH** gửi đề nghị phê duyệt (APR-001) loại "de_nghi_chi" lên **GD** để xem xét.
5. Đề nghị hiện đang chờ **GD** phê duyệt. Không có bước duyệt từ **KTT** trong quy trình này.

## Quy định áp dụng

- **KB-01**: Đề nghị chi có giá trị từ 0 đến không giới hạn cần được **GD (Giám đốc)** duyệt. Giá trị tối đa cho phép đề nghị chi là 30.000.000 đồng. Sai lệch giá trong biên bản không vượt quá 2% (theo quy định "gia": 0.02).
