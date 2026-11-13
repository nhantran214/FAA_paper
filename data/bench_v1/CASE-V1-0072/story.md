# Duyệt thư mời nhận việc khi người có thẩm quyền vắng mặt

Công ty TNHH Phân phối Minh An, hoạt động trong lĩnh vực phân phối thiết bị văn phòng và tài liệu in ấn, đang tiến hành quy trình tuyển dụng thêm 3 nhân viên giao hàng. Việc tuyển dụng này do Trưởng phòng nhân sự đề xuất và được gửi đến Giám đốc để phê duyệt. Tuy nhiên, Giám đốc hiện đang đi công tác nước ngoài và đã ủy quyền cho Phó giám đốc duyệt thay. Trong quá trình xử lý, hệ thống phát hiện rằng ủy quyền không bao gồm hạn mức cho việc tuyển dụng, dẫn đến việc quy trình bị dừng lại.

## Diễn biến

1. **DP-01** Khởi tạo quy trình tuyển dụng, tạo trường hợp "Duyệt thư mời nhận việc khi người có thẩm quyền vắng mặt".
2. **DE-NS** Tạo tài liệu đề xuất tuyển dụng với mã **DE-001**, yêu cầu tuyển 3 nhân viên giao hàng.
3. **DE-NS** Gửi phê duyệt cho **GD** với mã phê duyệt **APR-001**.
4. **DP-01** Kiểm tra quy trình phê duyệt, xác nhận người duyệt theo chính sách là **GD**. Phát hiện **PGD** không có thẩm quyền phê duyệt tuyển dụng.
5. **DP-01** Ghi nhận ngoại lệ: "Phó giám đốc không có quyền duyệt tuyển dụng nhân viên giao hàng theo ủy quyền".
6. **DP-01** Dừng quy trình do thiếu thẩm quyền phê duyệt.

## Quy định áp dụng

- **KB-01**: Quy trình phê duyệt đề xuất tuyển dụng yêu cầu người duyệt cuối cùng là Giám đốc (**GD**).
- **KB-02**: Quy định về ủy quyền phê duyệt yêu cầu phải có hạn mức rõ ràng cho từng loại phê duyệt.
- Chính sách phê duyệt tuyển dụng yêu cầu người duyệt là **GD**, không có quyền ủy quyền cho **PGD** trong trường hợp này.
- Hạn mức tuyển dụng tối đa là 3 nhân viên, phù hợp với đề xuất của **TP-NS**.
- Hệ thống không cho phép **PGD** phê duyệt vì không có thẩm quyền.

Quy trình dừng lại tại bước kiểm tra quyền phê duyệt, không có bước nào tiếp theo được thực hiện.
