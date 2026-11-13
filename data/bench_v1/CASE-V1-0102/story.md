# Xử lý nghỉ việc của nhân viên đã quá hạn bàn giao

Tại Công ty Cổ phần Phân phối Minh An, một nhân viên thuộc phòng Kinh doanh đã nghỉ việc từ ngày 20/03/2026. Theo quy định, quá trình bàn giao công việc phải được hoàn tất trước ngày 25/03/2026. Tuy nhiên, đến ngày 03/04/2026 vẫn chưa có thông báo hoàn tất, gây ra sự chậm trễ. Nhân sự điều phối phát hiện sự chậm trễ và báo cáo lên cấp trên, yêu cầu kiểm tra và xử lý phù hợp.

## Diễn biến

1. **DP-NV** khởi tạo trường hợp với tiêu đề "Xử lý quá hạn bàn giao của nhân viên nghỉ việc".
2. **DE-NV** tạo tài liệu **NV-01-YCBG** với loại chứng từ là yêu cầu và ghi chú là "Yêu cầu bàn giao công việc cho nhân viên nghỉ việc".
3. **DE-NV** gửi yêu cầu phê duyệt **APR-01** loại **yeu_cau_ban_giao** cho **TP-NV**.
4. **DE-NV** kiểm tra điều kiện: ngày bàn giao thực tế (03/04/2026) so với ngày bàn giao cuối cùng (25/03/2026), kết quả là quá hạn 9 ngày (quy định 5 ngày) và ghi nhận cờ.
5. **DE-NV** gửi yêu cầu phê duyệt **APR-02** loại **xu_ly_cham_tro** cho **GD**.
6. **DP-NV** đợi phê duyệt từ **GD** để tiếp tục quy trình.

## Quy định áp dụng

- **KB-01**: Quy trình xử lý nghỉ việc và bàn giao công việc yêu cầu phải hoàn tất bàn giao trong 5 ngày kể từ ngày nghỉ việc.
- **KB-02**: Quy trình phê duyệt xử lý chậm trễ bàn giao yêu cầu được phê duyệt bởi **GD** khi có dấu hiệu quá hạn.
