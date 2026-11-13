# Kiểm kê phát hiện hàng hóa hư hỏng trong kho

Công ty TNHH Phân phối Minh An là doanh nghiệp chuyên phân phối hàng tiêu dùng nhanh cho các siêu thị và cửa hàng tiện lợi trên toàn quốc, với quy mô 120 nhân viên và 30 cửa hàng bán lẻ, doanh thu hàng năm khoảng 200 tỷ VND. Trong quá trình kiểm kê định kỳ tại kho hàng TP.HCM, phát hiện một lô sản phẩm bột giặt X không khớp số lượng và bị hư hỏng, gây ra tổn thất tài sản và cần xử lý theo quy định nội bộ.

## Diễn biến

1. **DP-01** Khởi động trường hợp kiểm kê phát hiện hàng hóa hư hỏng, tạo trường hợp mới với tiêu đề "Kiểm kê phát hiện hàng hóa hư hỏng trong kho".
2. **THU-KHO-01** Lập biên bản kiểm tra, ghi nhận thiếu 200 sản phẩm và 200 sản phẩm bị hư hỏng, với biên bản có mã **BB-001**.
3. **DE-KT-01** Kiểm tra dữ liệu, phát hiện sai lệch vượt mức cho phép và ghi nhận cảnh báo về sự thiếu hụt.
4. **DE-KT-01** Tạo biên bản thanh lý **BB-002**, đề xuất thanh lý 400 sản phẩm bột giặt X với giá trị 6.600.000 đồng (đã bao gồm VAT 10%).
5. **DE-KT-01** Đề xuất phê duyệt xử lý hàng hóa hư hỏng với mã **APR-001**.
6. **DP-01** Chờ phê duyệt từ **KTT-01**, hiện đang dừng lại ở bước **S05**.

## Quy định áp dụng

- **KB-AP-01**: Quy trình phê duyệt xử lý hàng hóa hư hỏng yêu cầu duyệt bởi **KTT-01** (Kế toán trưởng) đối với giá trị dưới 10.000.000 đồng và **GD-01** (Giám đốc điều hành) với giá trị trên 10.000.000 đồng. Giá trị hư hỏng tối đa không cần báo cáo là 5.000.000 đồng.
