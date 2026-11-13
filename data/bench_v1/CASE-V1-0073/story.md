# Tiếp nhận nhân viên mới bị quá hạn xử lý

Công ty TNHH Siêu thị Minh An, một chuỗi siêu thị bán lẻ hoạt động tại TP. Hồ Chí Minh và Hà Nội, đang đối mặt với một trường hợp chậm trễ trong quy trình tiếp nhận nhân viên mới. Nhân viên Nguyễn Văn A được tuyển dụng vào ngày 15/03/2026, nhưng hồ sơ chưa hoàn tất do thiếu xác nhận bảo hiểm xã hội. Theo chính sách công ty, việc tiếp nhận nhân viên mới phải được xử lý trong 3 ngày làm việc, tức là hoàn tất trước ngày 20/03/2026. Tuy nhiên, đến ngày 21/03/2026, hệ thống tự động phát hiện việc xử lý bị quá hạn và báo cáo lên cấp quản lý.

## Diễn biến

1. **DP-NS** mở case với tiêu đề "Tiếp nhận nhân viên mới bị quá hạn xử lý".
2. **DE-NS** tạo văn bản **YE-001** yêu cầu xử lý ngoại lệ cho nhân viên **NV-01** (Nguyễn Văn A).
3. **DE-NS** kiểm tra điều kiện và phát hiện đã quá hạn 1 ngày so với cam kết 3 ngày, ghi nhận cờ cảnh báo.
4. **DE-NS** báo cáo sự việc là ngoại lệ với lý do "Quá hạn 1 ngày so với cam kết 3 ngày".
5. **DE-NS** yêu cầu phê duyệt **APR-001** loại "Xác nhận bảo hiểm xã hội".
6. **DE-NS** yêu cầu phê duyệt **APR-002** loại "Xử lý ngoại lệ".
7. **DP-NS** chờ phê duyệt từ **GD** cho **APR-002**, nhưng hiện chưa có quyết định nào.

## Quy định áp dụng

- **KB-02**: Chính sách thời gian xử lý hồ sơ nhân sự yêu cầu quá trình tiếp nhận nhân viên mới phải hoàn tất trong 3 ngày làm việc kể từ ngày tuyển dụng.
- **APR-001**: Loại phê duyệt "Xác nhận bảo hiểm xã hội" do **TP-NS** duyệt.
- **APR-002**: Loại phê duyệt "Xử lý ngoại lệ" do **GD** duyệt.
