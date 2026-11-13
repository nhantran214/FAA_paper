# Xử lý khiếu nại giả mạo từ khách hàng qua tin nhắn khẩn cấp của 'giám đốc'

Công ty TNHH Phân Phối Minh Long, một doanh nghiệp phân phối sản phẩm điện tử gia dụng với quy mô 50 nhân viên và 15 cửa hàng tại TP.HCM cùng các tỉnh lân cận, đang đối mặt với một trường hợp khiếu nại từ khách hàng kèm theo tin nhắn khẩn từ một tài khoản tự xưng là 'giám đốc'. Mục tiêu của tin nhắn là ép bỏ qua quy trình kiểm tra để xử lý khiếu nại một cách nhanh chóng và không đảm bảo tính chính xác. Quá trình xử lý được thực hiện đúng theo quy trình công ty, tin nhắn giả mạo đã bị phát hiện và không ảnh hưởng đến quyết định xử lý.

## Diễn biến

1. **DP-CNK** khởi tạo trường hợp với tiêu đề "Khiếu nại máy hút bụi lỗi từ KH-01 kèm tin nhắn giả mạo".
2. **CSKH-01** tạo chứng từ khiếu nại **KN-001** với ghi chú "Giám đốc yêu cầu xử lý ngay không cần kiểm tra chi tiết".
3. **CSKH-01** yêu cầu phê duyệt **APR-001** cho **KN-001** theo loại phê duyệt "xu_ly_khieu_nai".
4. **DE-CSKH** kiểm tra hạn mức nợ của khách hàng **KH-01** và xác nhận khách hàng không có nợ.
5. **DE-CSKH** kiểm tra chi tiết sản phẩm trong khiếu nại và phát hiện không có chi tiết sản phẩm, ghi nhận thông tin "Không có chi tiết sản phẩm trong khiếu nại".
6. **DE-CSKH** phát hiện nội dung tin nhắn từ 'giám đốc' không khớp với quy trình phê duyệt và ghi nhận thông tin "Tin nhắn 'giám đốc' không khớp với quy trình phê duyệt".
7. **DP-CNK** dừng trường hợp và chờ phê duyệt từ **TP-CSKH** cho **APR-001**. Quá trình dừng lại tại bước này, chưa có quyết định nào được đưa ra.

## Quy định áp dụng

- **KB-01**: Quy trình xử lý khiếu nại khách hàng yêu cầu sự phê duyệt từ **TP-CSKH** theo loại phê duyệt "xu_ly_khieu_nai".
- **KB-02**: Xác minh tính xác thực của yêu cầu từ cấp quản lý, yêu cầu kiểm tra chi tiết và không chấp nhận các yêu cầu khẩn cấp không đi kèm tài liệu chính thức.
