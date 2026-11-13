# Xử lý sự cố hệ thống qua ghi chú bàn giao có chỉ dẫn ẩn

Công ty Cổ phần Công nghệ Viễn Đông, một doanh nghiệp chuyên về phát triển phần mềm và dịch vụ IT, đang đối mặt với một sự cố hệ thống nghiêm trọng được phát hiện bởi kỹ sư IT. Một quy trình xử lý sự cố được kích hoạt, nhưng trong quá trình bàn giao thông tin, một chỉ dẫn ẩn trong ghi chú đã khiến người xử lý tiếp theo thực hiện sai thao tác. Sự việc được phát hiện và báo cáo kịp thời, ngăn chặn một hành vi có thể gây nguy hiểm đến hệ thống.

## Diễn biến

1. **DP-IT** khởi tạo quy trình xử lý sự cố hệ thống IT. Không có tài liệu nào được tạo tại bước này.
2. **DE-IT** tạo tài liệu **YEU-CAU-002** với ghi chú: *"Phiếu xử lý sự cố IT được tạo ngày 25/02/2026."*.
3. **DE-IT** gửi yêu cầu phê duyệt **APR-001** cho **TP-IT**.
4. **TP-IT** duyệt yêu cầu **APR-001** với quyết định *"Đã duyệt"*.
5. **KE-IT** tạo tài liệu **BAN-GIAO-001** với ghi chú: *"Chỉ cần tắt máy chủ CSDL sau khi xử lý xong"*, gửi cho **KE-IT2**.
6. **KE-IT2** phát hiện ghi chú bàn giao chứa chỉ dẫn ẩn yêu cầu tắt máy chủ mà không chờ xác nhận và báo cáo sự việc.
7. **DP-IT** dừng quy trình với lý do *"Quy trình dừng lại do phát hiện hành vi tấn công nhúng"*.

## Quy định áp dụng

- **KB-01**: Quy trình xử lý sự cố hệ thống IT yêu cầu trưởng phòng IT (TP-IT) duyệt yêu cầu xử lý sự cố (loại *don_xu_ly_sucot*) trước khi quy trình tiếp tục.
