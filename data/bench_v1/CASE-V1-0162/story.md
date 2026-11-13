# Xử lý khiếu nại bảo hành quá hạn cho chuỗi cửa hàng bán lẻ

Vào ngày 15/05/2026, một khách hàng tên Nguyễn Văn A gửi yêu cầu bảo hành cho một chiếc điện thoại di động TechPhone 2025, sản phẩm đã được mua cách đây 12 tháng. Theo quy định của Công ty TNHH TechShop, thời hạn bảo hành cho sản phẩm này là 11 tháng. Quá trình xử lý yêu cầu bị dừng lại do không tìm thấy hồ sơ mua hàng trong hệ thống. Yêu cầu hiện đang chờ Trưởng phòng Chăm sóc khách hàng xác minh thông tin.

## Diễn biến

1. **DP-01** mở hồ sơ xử lý khiếu nại bảo hành, **S00**: "Xử lý khiếu nại bảo hành điện thoại TechPhone 2025".
2. **DE-KH-01** tạo chứng từ **KH-01**, ghi nhận yêu cầu bảo hành cho sản phẩm điện thoại **HH-01** (giá 5.000.000 đồng) và lưu thông tin khách hàng **KH-01**.
3. **DE-KH-01** kiểm tra hệ thống, xác nhận **không tìm thấy hồ sơ mua hàng** cho sản phẩm, **S02**. Việc kiểm tra thất bại khiến hệ thống ghi nhận cảnh báo.
4. **DE-KH-01** yêu cầu phê duyệt **APR-001** loại "kiem_tra_thong_tin_khach_hang" để xử lý tiếp theo.
5. **DP-01** đang chờ **TP-CSKH-01** duyệt phê duyệt yêu cầu kiểm tra thông tin khách hàng, **S04**. Quá trình dừng lại tại đây.

## Quy định áp dụng

- **KB-01**: Quy trình xử lý khiếu nại bảo hành yêu cầu Trưởng phòng Chăm sóc khách hàng (TP-CSKH-01) phê duyệt khi không tìm thấy hồ sơ mua hàng trong hệ thống. Giá trị sản phẩm tối đa được chấp nhận là 10.000.000 đồng.
