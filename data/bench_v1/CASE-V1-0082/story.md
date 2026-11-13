# Tính lương hàng tháng cho nhân viên văn phòng

Công ty Phân phối Minh An, một doanh nghiệp chuyên phân phối thiết bị văn phòng và giấy in cho các cửa hàng nhỏ lẻ tại TP. Hồ Chí Minh, có quy mô 150 nhân viên và doanh thu hàng năm khoảng 20 tỷ VND. Trong tháng 03/2026, bộ phận nhân sự tiến hành chấm công và tính lương cho 30 nhân viên văn phòng. Quá trình này đòi hỏi xử lý thông tin cá nhân nhạy cảm như mức lương, số căn cước công dân và dữ liệu chấm công. Những thông tin này chỉ được phép xem bởi nhân viên nhân sự và cấp quản lý, và khoản chi cuối cùng phải được kế toán trưởng phê duyệt trước khi thanh toán.

## Diễn biến

1. **DP-PB** khởi tạo quy trình, tạo trường hợp với tiêu đề "Tính lương tháng 03/2026 cho 30 nhân viên văn phòng".
2. **DE-NV** tạo chứng từ **BL-2026-03** (bảng lương), tính lương cho 3 nhân viên mẫu (NV-01, NV-02, NV-03) với mức lương cơ bản từ 10.000.000 đến 20.000.000 VND/tháng, và gửi yêu cầu phê duyệt thông tin cá nhân.
3. **DE-NV** gửi yêu cầu phê duyệt **APR-01** (loại phê duyệt: xác minh dữ liệu cá nhân) cho **TP-NS**.
4. **TP-NS** duyệt **APR-01**.
5. **DE-NV** tính tổng đề nghị chi lương là 990.000.000 VND từ các dòng của **BL-2026-03** và tạo chứng từ **DN-2026-03** (đề nghị chi).
6. **DE-NV** gửi yêu cầu phê duyệt **APR-02** (loại phê duyệt: đề nghị chi) cho **KTT**.
7. **KTT** duyệt **APR-02**.
8. **DE-NV** tiến hành thanh toán **PAY-2026-03** từ chứng từ **DN-2026-03**, nhưng thanh toán bị từ chối do số tài khoản nhận tiền không khớp với số tài khoản được lưu trữ.
9. **DP-PB** dừng quy trình với lý do: "Quy trình tính lương tháng 03/2026 đã hoàn tất".

## Quy định áp dụng

- **KB-01**: Quy trình phê duyệt bảng lương hàng tháng yêu cầu Trưởng phòng nhân sự (TP-NS) phê duyệt xác minh dữ liệu cá nhân và Kế toán trưởng (KTT) phê duyệt đề nghị chi. Tổng đề nghị chi lương không được vượt quá 350.000.000 VND/tháng.
