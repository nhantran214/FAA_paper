# Xử lý khiếu nại quá hạn của khách hàng

Công ty Cổ phần Phần Mềm Minh Huy (Minh Huy), một công ty có quy mô 50 nhân viên và doanh thu hàng năm khoảng 15 tỷ VND, cung cấp phần mềm quản lý doanh nghiệp cho các công ty vừa và nhỏ tại Việt Nam. Trong trường hợp này, một khách hàng đã gửi khiếu nại về lỗi phần mềm và phản hồi chậm, vượt quá 3 ngày làm việc theo cam kết của công ty. Việc xử lý chậm trễ này được hệ thống phát hiện và đánh dấu là ngoại lệ, yêu cầu đánh giá lại quy trình để đảm bảo cải thiện trải nghiệm khách hàng và tuân thủ cam kết.

## Diễn biến

1. **DP-MH** mở trường hợp khiếu nại với tiêu đề "Khiếu nại quá hạn về lỗi phần mềm của KH-01".
2. **DE-CSKH** tạo chứng từ khiếu nại **KN-001** với ghi chú "Khách hàng báo lỗi phần mềm và phản hồi chậm".
3. **DE-CSKH** kiểm tra thời gian xử lý: ngày hiện tại (03 ngày) đã vượt quá hạn xử lý (03 ngày làm việc). Việc xử lý bị đánh dấu là **quá hạn**.
4. **DE-CSKH** ghi nhận ngoại lệ: chưa phản hồi khiếu nại trong 3 ngày làm việc theo quy định.
5. **DE-CSKH** yêu cầu phê duyệt đánh giá lại khiếu nại từ **TP-CSKH** với mã duyệt **APR-001**.
6. **DP-MH** đang chờ phê duyệt từ **TP-CSKH**. Quá trình xử lý tạm dừng tại bước này.

## Quy định áp dụng

- **KB-01**: Quy trình xử lý khiếu nại khách hàng yêu cầu Trưởng phòng Chăm sóc khách hàng (TP-CSKH) phê duyệt việc đánh giá lại khiếu nại khi quá hạn xử lý.
