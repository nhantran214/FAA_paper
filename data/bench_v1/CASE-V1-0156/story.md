# Hoàn tiền cho khách hàng do thiếu hóa đơn

Công ty TNHH Giao Hàng Nhanh, một doanh nghiệp chuyên cung cấp dịch vụ giao hàng nhanh tại khu vực miền Nam, đang xử lý một hồ sơ hoàn tiền cho khách hàng. Số tiền cần hoàn là 1.200.000 VND cho dịch vụ giao hàng bị hủy ngày 15/02/2026. Tuy nhiên, hồ sơ thiếu hóa đơn bán hàng bắt buộc, khiến quy trình phải dừng lại để chờ khách hàng bổ sung tài liệu.

## Diễn biến

1. DP-01 mở hồ sơ hoàn tiền với tiêu đề "Hoàn tiền cho khách hàng do thiếu hóa đơn".
2. DE-KT-02 tạo chứng từ DNHU-001 để đề nghị hoàn ứng 1.200.000 VND cho dịch vụ giao hàng bị hủy.
3. DE-KT-02 kiểm tra và phát hiện thiếu hóa đơn bán hàng, đánh dấu chứng từ DNHU-001 với lý do "Thiếu hóa đơn bán hàng bắt buộc".
4. DE-KT-02 yêu cầu phê duyệt APR-001 để yêu cầu khách hàng bổ sung tài liệu.
5. DE-KT-02 thực hiện thanh toán PAY-001 nhưng bị từ chối do APR-001 chưa được duyệt.
6. DP-01 chờ phê duyệt từ KTT-01 để tiếp tục xử lý.

## Quy định áp dụng

- KB-01: Yêu cầu hóa đơn bán hàng hoặc bản sao hóa đơn khi đề nghị hoàn tiền. Số tiền hoàn tiền không được vượt quá 5.000.000 VND. Phê duyệt yêu cầu hoàn tiền do KTT-01 (Kế toán trưởng) thực hiện.
