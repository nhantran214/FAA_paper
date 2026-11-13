# Chấm công và tính lương tháng 03/2026 cho nhân viên cửa hàng

Công ty Cổ phần Siêu Thị Toàn Cầu (GSS), một doanh nghiệp bán lẻ với 30 cửa hàng trên toàn quốc, có 1.800 nhân viên đang hoạt động. Đầu tháng 04/2026, bộ phận Nhân sự của GSS đã tiến hành quy trình chấm công và tính lương cho tháng 03/2026, đảm bảo tính minh bạch và chính xác trong việc thanh toán lương cho toàn bộ nhân viên. Quy trình này được thực hiện tự động thông qua hệ thống số và được phê duyệt bởi các cấp có thẩm quyền trước khi hoàn tất.

## Diễn biến

1. **DP-NS** mở case "Chấm công và tính lương tháng 03/2026" để bắt đầu quy trình.
2. **DE-NS** tạo bảng lương "BL-03-2026" từ dữ liệu chấm công của 1.800 nhân viên, tổng hợp 4 khoản lương với các mức từ 8.000.000 đến 30.000.000 đồng.
3. **DE-NS** gửi phê duyệt cho **TP-NS** yêu cầu xác nhận bảng lương "BL-03-2026".
4. **TP-NS** duyệt bảng lương ngày 07/04/2026 với tổng giá trị 76.375.000 đồng.
5. **DE-NS** gửi phê duyệt cho **GD-KT** yêu cầu duyệt bảng lương "BL-03-2026" theo quy định tài chính.
6. **GD-KT** duyệt bảng lương ngày 09/04/2026 với cùng giá trị 76.375.000 đồng.
7. **DP-NS** dừng case ngày 10/04/2026 sau khi quy trình hoàn tất với cả hai phê duyệt.

## Quy định áp dụng

- **KB-001**: Quy trình chấm công và tính lương yêu cầu sự phê duyệt từ Trưởng phòng Nhân sự (TP-NS) và Giám đốc Tài chính (GD-KT). Tổng lương tháng không được vượt quá 20.000.000 đồng/nhân viên theo quy định ngân sách.
