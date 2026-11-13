# Cấp quyền truy cập hệ thống ERP cho nhân viên mới phòng CNTT

Công ty Cổ phần Giao hàng Nhanh Việt Nam, một doanh nghiệp cung cấp dịch vụ vận tải và logistics có quy mô 200 nhân sự và doanh thu 1.200 tỷ VND/năm, đã thực hiện quy trình cấp quyền truy cập hệ thống ERP cho một nhân viên mới thuộc phòng Công nghệ Thông tin. Việc cấp quyền này là cần thiết để nhân viên có thể làm việc hiệu quả và đảm bảo tính an toàn thông tin của hệ thống.

## Diễn biến

1. **DP-01** Khởi tạo quy trình với tiêu đề "Cấp quyền ERP cho nhân viên mới NV-CNTT-01".
2. **DE-CNTT** Tạo văn bản yêu cầu có mã **YEUCAU-001**, bao gồm 1 mục yêu cầu: "Quyền truy cập ERP" với số lượng 1.
3. **DE-CNTT** Gửi yêu cầu phê duyệt **APR-001** liên quan đến **YEUCAU-001** theo loại phê duyệt **yeu_cau_cap_quyen**.
4. **TP-CNTT** Phê duyệt yêu cầu **APR-001** với quyết định "Đã duyệt".
5. **IT-SYSTEM** Tạo văn bản xác nhận **XACNHAN-001** với ghi chú: "Hệ thống ERP đã cấp quyền truy cập".
6. **IT-SYSTEM** Cập nhật trạng thái nhân sự **NV-CNTT-01** thành "Đang làm".
7. **DP-01** Kết thúc quy trình với lý do: "Quyền truy cập đã được cấp thành công".

## Quy định áp dụng

- **KB-01**: Quy trình phê duyệt cấp quyền truy cập hệ thống ERP yêu cầu sự phê duyệt của **TP-CNTT** (Trưởng phòng CNTT) theo loại phê duyệt **yeu_cau_cap_quyen**.
