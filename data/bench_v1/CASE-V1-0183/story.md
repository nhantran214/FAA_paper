# Chấm dứt hợp đồng cung cấp thiết bị POS khi hợp đồng hết hạn

Công ty Cổ phần Siêu Thị Minh Long, một chuỗi 35 cửa hàng bán lẻ với doanh thu hàng năm khoảng 500 tỷ VND, đang xử lý một giao dịch bất thường từ nhà cung cấp thiết bị POS sau khi hợp đồng đã hết hiệu lực. Hóa đơn yêu cầu thanh toán 3 thiết bị POS với tổng giá trị 36.000.000 đồng được gửi vào ngày 05/01/2026, nhưng hợp đồng cung ứng đã chấm dứt từ ngày 01/01/2026. Việc từ chối thanh toán là cần thiết để đảm bảo tuân thủ pháp lý và kiểm soát chi phí.

## Diễn biến

1. **DP-PL** tạo case và điều phối quy trình chấm dứt hợp đồng sau khi phát hiện giao dịch bất thường, hóa đơn **HD-PL-0012** yêu cầu thanh toán 3 thiết bị POS từ **NCC-01**.
2. **DE-PL** kiểm tra trạng thái hợp đồng **HD-2024-PL001** và xác nhận hợp đồng đã hết hiệu lực, đánh dấu giao dịch là không hợp lệ.
3. **DE-PL** tạo biên bản **PD-STOP-001** để ghi nhận việc từ chối thanh toán, yêu cầu phê duyệt từ người có thẩm quyền.
4. **DE-PL** gửi yêu cầu phê duyệt **PD-APR-001** để xác nhận việc từ chối thanh toán.
5. **KTT** phê duyệt yêu cầu **PD-APR-001**, xác nhận hợp đồng hết hiệu lực và từ chối giao dịch.
6. **DE-PL** thực hiện bước **S05** để thanh toán, nhưng bị từ chối do hóa đơn **HD-PL-0012** không được khớp và không có phê duyệt thanh toán trực tiếp.
7. **DP-PL** chấm dứt case với lý do hợp đồng hết hiệu lực, từ chối thanh toán hóa đơn.

## Quy định áp dụng

- **KB-PL-01**: Hướng dẫn xử lý hợp đồng hết hạn và giao dịch không hợp lệ, quy định rằng người có thẩm quyền phê duyệt dừng thanh toán là **KTT** (Kế toán trưởng).
