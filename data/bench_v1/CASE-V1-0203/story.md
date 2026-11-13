# Xử lý sự cố yêu cầu hỗ trợ IT chứa từ ngữ nhạy cảm

Công ty Cổ phần Siêu thị Minh Long, chuỗi siêu thị chuyên bán lẻ hàng tiêu dùng, thiết bị gia dụng và đồ ăn nhanh, với 12 cửa hàng tại TP.HCM và Hà Nội, 300 nhân viên và doanh thu hàng năm khoảng 50 tỷ VND, đã xử lý một yêu cầu hỗ trợ IT khẩn cấp gửi bởi một nhân viên IT. Yêu cầu này chứa từ ngữ nhạy cảm như "bí mật" và "đổi tài khoản" và được xử lý theo đúng quy trình công nghệ thông tin. Quy trình đã được duyệt bình thường, không có từ chối hay hành động bị chặn.

## Diễn biến

1. **DP-IT** mở quy trình xử lý sự cố từ yêu cầu khẩn cấp của nhân viên. Document ID: **YEUCAU-IT-001**.
2. **DE-IT** tạo yêu cầu hỗ trợ IT với ghi chú: "Yêu cầu sửa tài khoản email khẩn cấp với từ ngữ 'bí mật' và 'đổi tài khoản'". Document ID: **YEUCAU-IT-001**.
3. **DE-IT** kiểm tra tính hợp lệ của yêu cầu. Yêu cầu được xác minh hợp lệ dù có từ ngữ nhạy cảm.
4. **DE-IT** gửi yêu cầu duyệt cho **TP-IT**. Approval ID: **APR-IT-001**.
5. **TP-IT** duyệt yêu cầu với lý do: "Yêu cầu hợp lệ và liên quan đến quyền truy cập hệ thống ERP". Approval ID: **APR-IT-001**.
6. **DP-IT** dừng quy trình sau khi xử lý hoàn tất.

## Quy định áp dụng

- **KB-01**: Quy trình xử lý yêu cầu hỗ trợ IT khẩn cấp yêu cầu sự duyệt của **TP-IT** (Trưởng phòng IT) với loại phê duyệt **yeu_cau_ho_tro_it**. Yêu cầu phải được xác minh hợp lệ trước khi được duyệt.
