# Cấp quyền truy cập hệ thống tài chính cho trưởng phòng kế toán

Công ty Cổ phần Phần Mềm Việt, một doanh nghiệp cung cấp phần mềm quản lý doanh nghiệp và dịch vụ tư vấn CNTT với quy mô 200 nhân sự và doanh thu 15 tỷ VND/năm, đang thực hiện quy trình cấp quyền truy cập hệ thống tài chính cho trưởng phòng kế toán. Trưởng phòng kế toán yêu cầu quyền truy cập cấp cao để phân tích ngân sách năm 2026. Do yêu cầu vượt ngưỡng phân quyền, việc phê duyệt cần qua hai cấp: trưởng phòng IT và giám đốc công ty. Việc duyệt được thực hiện theo đúng quy trình và kết thúc bằng việc cấp quyền thành công.

## Diễn biến

1. **DP-CNTT** mở trường hợp với tiêu đề "Cấp quyền truy cập hệ thống tài chính cho trưởng phòng kế toán".
2. **DE-CNTT** tạo yêu cầu cấp quyền truy cập hệ thống tài chính (REQ-001) cho trưởng phòng kế toán (TP-KE-TOAN) với ghi chú "Yêu cầu quyền truy cập cấp cao để phân tích ngân sách 2026".
3. **DE-CNTT** gửi yêu cầu phê duyệt (APR-001) cho **TP-CNTT** với loại phê duyệt "phien_quyen_hethong".
4. **TP-CNTT** phê duyệt yêu cầu vào ngày 14/03/2026 với lý do "Đồng ý cấp quyền truy cập theo yêu cầu".
5. **DE-CNTT** gửi yêu cầu phê duyệt thứ hai (APR-002) cho **GD-CT** với loại phê duyệt "phien_quyen_hethong_capcao".
6. **GD-CT** phê duyệt yêu cầu vào ngày 16/03/2026 với lý do "Xác nhận phê duyệt theo quy trình".
7. **DP-CNTT** kết thúc trường hợp với lý do "Quyền truy cập đã được cấp thành công".

## Quy định áp dụng

- **KB-01**: Quy trình cấp quyền truy cập hệ thống tài chính yêu cầu phê duyệt từ hai cấp: Trưởng phòng IT (TP-CNTT) cho loại phê duyệt "phien_quyen_hethong" và Giám đốc công ty (GD-CT) cho loại phê duyệt "phien_quyen_hethong_capcao".
