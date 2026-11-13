# Xử lý đơn trả hàng từ khách hàng do lỗi phần mềm

Công ty Cổ phần Phần Mềm TechPlus với quy mô 300 nhân viên và doanh thu 30 tỷ VND/năm, đang xử lý một yêu cầu hoàn tiền từ khách hàng do lỗi cài đặt sai phiên bản phần mềm. Khách hàng là công ty TNHH Minh Anh (KH-01) yêu cầu hoàn lại 5.000.000 đồng. Quá trình bắt đầu với việc kỹ sư chăm sóc khách hàng (DE-CSKH) lập đơn hoàn tiền và gửi duyệt. Tuy nhiên, do số tiền vượt ngưỡng phê duyệt của kỹ sư, đơn bị dừng lại ở bước duyệt của trưởng phòng chăm sóc khách hàng (TP-CSKH).

## Diễn biến

1. **DP-01** khởi tạo quy trình với tiêu đề "Xử lý hoàn tiền lỗi cài đặt phần mềm", không có tài liệu liên quan.
2. **DE-CSKH** tạo tài liệu hoàn tiền **PHIEU-DOI-001** cho khách hàng **KH-01** với nội dung: 1 lần dịch vụ cài đặt và hỗ trợ phần mềm **DV-01**, đơn giá 5.000.000 đồng, bao gồm thuế VAT 10%, tổng tiền là 5.500.000 đồng.
3. **DE-CSKH** gửi đơn hoàn tiền **APR-001** đến **TP-CSKH** để phê duyệt.
4. **DP-01** dừng quy trình tại bước **S03** để chờ **TP-CSKH** phê duyệt **APR-001**. Đến thời điểm này, chưa có quyết định nào được đưa ra.

## Quy định áp dụng

- **KB-01**: Chính sách hoàn tiền cho khách hàng do lỗi kỹ thuật yêu cầu: tất cả các đơn hoàn tiền, bất kể giá trị (từ 3.000.000 đến 5.000.000 đồng hoặc trên 5.000.000 đồng) đều phải được phê duyệt bởi **TP-CSKH**. Kỹ sư chăm sóc khách hàng (DE-CSKH) không có quyền phê duyệt bất kỳ đơn hoàn tiền nào.
