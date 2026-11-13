# Chuyển 200 thùng xe hàng từ kho TP.HCM sang kho Hà Nội

Công ty Vận Tải Hồng Minh với quy mô 150 nhân viên, 30 xe tải và 2 kho hàng lớn, đang thực hiện quy trình chuyển 200 thùng xe hàng từ kho TP.HCM sang kho Hà Nội theo yêu cầu của thủ kho Hà Nội. Đây là một hoạt động thường xuyên trong việc quản lý và phân phối hàng hóa nội địa, đảm bảo hiệu quả và đúng quy định.

## Diễn biến

1. **DP** khởi tạo quy trình với tiêu đề "Chuyển 200 thùng xe hàng từ kho TP.HCM sang kho Hà Nội".
2. **DE-KH** tạo phiếu xuất **PX-CHUYEN-01**, ghi nhận 200 thùng xe hàng với đơn giá 250.000 đồng/thùng, có VAT 10% (25.000 đồng/thùng).
3. **DE-KH** yêu cầu phê duyệt **APR-CHUYEN-01** cho phiếu xuất **PX-CHUYEN-01**.
4. **DE-KH** kiểm tra số lượng 200 thùng so với hạn mức chuyển kho là 200, không phát sinh cảnh báo.
5. **TP-KHO** duyệt yêu cầu **APR-CHUYEN-01**.
6. **VTV** ghi nhận vận chuyển thành công từ TP.HCM sang Hà Nội.
7. **THU-KHO-HN** tạo phiếu nhập **PN-CHUYEN-01** ghi nhận 200 thùng xe hàng không hư hại.
8. **DP** kết thúc quy trình với lý do "Quy trình chuyển kho hoàn tất thành công".

## Quy định áp dụng

- **KB-01**: Quy trình phê duyệt yêu cầu chuyển kho yêu cầu phê duyệt của **TP-KHO** (Trưởng phòng Kho TP.HCM), với hạn mức chuyển kho là 200 đơn vị.

Quy trình đảm bảo tính minh bạch và tuân thủ, không có ngoại lệ hoặc cảnh báo nào xảy ra.
