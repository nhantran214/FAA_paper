# Xử lý nợ quá hạn trong khóa sổ cuối tháng

Công ty TNHH Phân phối Minh An, một doanh nghiệp có quy mô 30 nhân viên và 15 cửa hàng bán lẻ, đang đối mặt với một khoản phải thu từ khách hàng KH-05 vượt quá hạn thanh toán 3 ngày. Trong quá trình khóa sổ cuối tháng, hệ thống phát hiện khoản nợ này và quy trình xử lý nợ quá hạn đã được khởi động. Việc xử lý cần sự phê duyệt từ Giám đốc theo chính sách nội bộ, và quy trình hiện đang chờ phê duyệt.

## Diễn biến

1. **DP-KT** khởi tạo quy trình xử lý nợ quá hạn KH-05, tạo hồ sơ cho trường hợp này.
2. **DE-KT** tự động tạo văn bản yêu cầu PH-001 để đề xuất gửi nhắc nợ và phương án xử lý đối với KH-05.
3. **DE-KT** đánh dấu trường hợp KH-05 như một ngoại lệ do khoản nợ quá hạn 3 ngày.
4. **DE-KT** kiểm tra xem số ngày quá hạn có vượt ngưỡng cho phép theo chính sách. Khoản nợ 3 ngày vẫn trong giới hạn 30 ngày nên không bị từ chối.
5. **KTT** đề xuất phương án xử lý nợ và gửi yêu cầu phê duyệt APR-001 cho Giám đốc (GD) theo quy định.
6. **DP-KT** đang chờ **GD** phê duyệt phương án xử lý nợ APR-001. Hiện chưa có hành động nào được thực hiện sau bước này.

## Quy định áp dụng

- **KB-01**: Chính sách xử lý nợ quá hạn quy định rằng các khoản nợ quá hạn đến 30 ngày cần được phê duyệt bởi Giám đốc (GD). Việc gửi nhắc nợ và đề xuất phương án xử lý phải được duyệt trước khi thực hiện.
