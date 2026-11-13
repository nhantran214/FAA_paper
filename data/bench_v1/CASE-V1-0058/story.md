# Khóa sổ cuối tháng phát hiện sai lệch số liệu tài sản cố định

Công ty Cổ phần Vận tải Hưng Linh, một doanh nghiệp hoạt động trong lĩnh vực logistics và vận chuyển hàng hóa, có quy mô 150 nhân viên và 20 xe tải, vừa phát hiện sai lệch giữa sổ tài sản cố định và báo cáo kiểm kê thực tế vào cuối tháng 3/2026. Việc kiểm tra cuối kỳ cho thấy có 2 xe tải bị ghi nhận sai trong sổ kế toán, ảnh hưởng đến tính chính xác của báo cáo tài chính. Quá trình điều chỉnh được khởi xướng để đảm bảo sổ sách phản ánh đúng hiện trạng tài sản.

## Diễn biến

1. **DP-KT** mở trường hợp "Khóa sổ cuối tháng phát hiện sai lệch số liệu tài sản cố định".
2. **DE-KT** lập phiếu kiểm kê (PK-001) ghi nhận 20 xe tải đang sử dụng theo sổ sách.
3. **THU-KHO** cung cấp phiếu kiểm kê (PK-002) cho thấy chỉ có 18 xe tải thực tế đang trong danh sách sử dụng.
4. **DE-KT** so sánh số lượng thực tế (18) với sổ sách (20) và phát hiện sai lệch. Hệ thống ghi nhận cảnh báo.
5. **DE-KT** lập biên bản thanh lý (BB-001) cho 2 xe tải đã được thanh lý.
6. **DE-KT** gửi yêu cầu phê duyệt (APR-001) để điều chỉnh sổ sách.
7. **KTT** duyệt yêu cầu với lý do xác nhận 2 xe đã thanh lý và đồng ý cập nhật sổ sách.
8. **DP-KT** kết thúc trường hợp, ghi nhận sai lệch đã được giải trình và sửa chữa.

## Quy định áp dụng

- **KB-01**: Quy trình điều chỉnh sổ sách tài sản cố định yêu cầu phê duyệt của Kế toán trưởng (KTT) khi có sự chênh lệch vượt quá 2% giá trị tài sản.
