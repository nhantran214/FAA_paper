# Hoàn tiền cho khách hàng do lỗi sản phẩm

Công ty Cổ phần Phần mềm Việt, một công ty chuyên cung cấp phần mềm quản lý doanh nghiệp cho các doanh nghiệp vừa và nhỏ, đã xử lý một yêu cầu hoàn tiền cho khách hàng KH-01 do lỗi phần mềm đã mua. Số tiền hoàn là 5.500.000 VND, bao gồm cả thuế VAT 10%, và đã được thực hiện theo đúng quy trình nội bộ cũng như chính sách phê duyệt.

## Diễn biến

1. **DP-01** tạo case hoàn tiền với tiêu đề "Hoàn tiền lỗi phần mềm cho KH-01".
2. **KH-01** gửi hóa đơn mua hàng (HD-001) cho phần mềm HH-01 với giá 5.000.000 VND.
3. **DE-CSKH-01** tạo đơn bán hàng (DON-001) và phiếu xuất (PX-001) để đối chiếu với hóa đơn mua hàng.
4. **DE-CSKH-01** đối chiếu (reconcile) hóa đơn HD-001 với đơn bán DON-001 và phiếu xuất PX-001, cả hai đều khớp.
5. **DE-CSKH-01** tạo đơn đề nghị hoàn ứng (DE-001) và gửi duyệt yêu cầu hoàn tiền.
6. **KT-01** phê duyệt yêu cầu hoàn tiền (APR-001) với số tiền 5.500.000 VND.
7. **DE-CSKH-01** thực hiện thanh toán (PAY-001) cho khách hàng KH-01 vào tài khoản ngân hàng 1234567890123456.
8. **DP-01** dừng case với lý do "Hoàn tiền thành công".

## Quy định áp dụng

- **KB-01**: Chính sách hoàn tiền do lỗi sản phẩm: Các yêu cầu hoàn tiền với giá trị ≤ 10.000.000 VND sẽ được phê duyệt bởi Kế toán trưởng (KT-01), còn các yêu cầu lớn hơn sẽ cần sự phê duyệt của Giám đốc (GD-01).
