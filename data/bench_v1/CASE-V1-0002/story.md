# Cập nhật số tài khoản nhận tiền của nhà cung cấp giấy in

Công ty TNHH Văn Phòng Phẩm Minh Hùng, một công ty chuyên phân phối văn phòng phẩm và thiết bị in ấn cho các doanh nghiệp vừa và nhỏ tại TP.HCM và Bình Dương, đã thực hiện một quy trình cập nhật số tài khoản ngân hàng của nhà cung cấp giấy in NCC-01. Việc đổi tài khoản này là cần thiết để đảm bảo các khoản thanh toán cho nhà cung cấp được thực hiện chính xác và đúng thời hạn, tránh rủi ro về giao dịch không thành công do thông tin tài khoản cũ không còn hợp lệ.

## Diễn biến

1. **DP-01** khởi tạo hồ sơ "Cập nhật số tài khoản nhà cung cấp giấy in", bắt đầu quy trình.
2. **DE-KT** tạo phụ lục hợp đồng **PLHD-001** với nội dung đề nghị đổi số tài khoản từ 123456789 sang 987654321.
3. **DE-KT** kiểm tra thông tin tài khoản mới 987654321 qua hệ thống ngân hàng vào ngày 18/03/2026, xác định tài khoản hợp lệ.
4. **DE-KT** gửi yêu cầu phê duyệt **APR-001** cho **KTT** để xử lý thay đổi tài khoản.
5. **KTT** phê duyệt yêu cầu đổi tài khoản vào ngày 20/03/2026, với lý do "Thông tin tài khoản mới đã được xác minh".
6. **DE-KT** cập nhật tài khoản mới bằng phụ lục hợp đồng **PLHD-001-CAP**, ghi rõ thay đổi số tài khoản thành 987654321.
7. **DP-01** dừng quy trình với lý do "Đã cập nhật tài khoản nhà cung cấp".

## Quy định áp dụng

- **KB-01**: Quy trình cập nhật thông tin tài khoản ngân hàng của nhà cung cấp yêu cầu kiểm tra thông tin tài khoản mới qua hệ thống ngân hàng độc lập và phê duyệt bởi Kế toán trưởng (KTT).
