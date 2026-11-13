# Gia hạn hợp đồng phần mềm bị quá hạn

Công ty Cổ phần Công nghệ Thông tin Minh Hải, một doanh nghiệp có quy mô 150 nhân viên và doanh thu hàng năm khoảng 20 tỷ VND, đang xử lý một trường hợp gia hạn hợp đồng phần mềm bị quá hạn. Hợp đồng bản quyền phần mềm với khách hàng KH-01 đã hết hiệu lực vào ngày 01/10/2025, nhưng vẫn có giao dịch phát sinh vào ngày 15/01/2026. Bộ phận pháp chế phát hiện sự việc và đề xuất gia hạn hợp đồng để đảm bảo tính pháp lý và duy trì mối quan hệ với khách hàng.

## Diễn biến

1. **DP-CT** khởi tạo quy trình "Gia hạn hợp đồng phần mềm bị quá hạn".
2. **DE-PC** kiểm tra trạng thái hợp đồng, phát hiện hợp đồng đã hết hiệu lực và ghi nhận cảnh báo tại bước **S01**, tài liệu **HD-01**.
3. **DE-PC** tạo tài liệu hợp đồng **HD-01** và phụ lục hợp đồng **HD-01-PL** với phần mềm **HH-01** (đơn giá 15.000.000 VND, VAT 10%) cho khách hàng **KH-01**.
4. **DE-PC** yêu cầu phê duyệt gia hạn hợp đồng với mã **APR-01**.
5. **DP-CT** đang chờ **GD-C** phê duyệt yêu cầu **APR-01**.

## Quy định áp dụng

- **KB-01**: Quy trình gia hạn hợp đồng bản quyền phần mềm yêu cầu Giám đốc công ty (**GD-C**) phê duyệt các đề xuất gia hạn hợp đồng.
