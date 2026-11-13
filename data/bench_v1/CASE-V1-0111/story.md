# Nhập 10.000 sản phẩm điện tử từ nhà cung cấp cho chuỗi bán lẻ

Công ty TNHH Điện Tử Minh Phát, một doanh nghiệp chuyên phân phối và bán lẻ sản phẩm điện tử gia đình với quy mô 250 nhân viên và 35 cửa hàng tại Hà Nội và TP.HCM, đang thực hiện một đơn hàng lớn để nhập 10.000 sản phẩm từ nhà cung cấp NCC-01. Đơn hàng có giá trị chưa VAT là 164.996.700.000 VND, với VAT 10% là 16.499.670.000 VND, tổng cộng 181.496.370.000 VND. Việc nhập hàng được yêu cầu gấp do hàng tồn kho đang ở mức thấp, và quá trình được phê duyệt đầy đủ ở từng cấp trước khi nhập kho thành công.

## Diễn biến

1. **DP-MP** khởi tạo quy trình, tạo ra vụ việc với tiêu đề "Nhập 10.000 sản phẩm điện tử từ nhà cung cấp cho chuỗi bán lẻ".
2. **DE-KH** tạo đơn mua hàng **PO-MP-2604** với 10.000 sản phẩm từ NCC-01, bao gồm 3333 sản phẩm HH-01, 3334 sản phẩm HH-02 và 3333 sản phẩm HH-03, giá 18.000.000 VND/sản phẩm.
3. **DE-KH** gửi yêu cầu phê duyệt đơn nhập kho **APR-PO-2604**.
4. **GD-MP** phê duyệt đơn nhập kho **APR-PO-2604** với giá trị 181.496.370.000 VND (gồm VAT).
5. **DE-KH** tạo đề nghị chi **DN-CHI-2604** cho số tiền 54.994.500.000 VND (gồm VAT).
6. **DE-KH** gửi yêu cầu phê duyệt đề nghị chi **APR-DN-2604**.
7. **TP-KT** phê duyệt đề nghị chi **APR-DN-2604**.
8. **NCC-01** giao hàng trong 24 giờ theo van đơn **VAN-2604**.
9. **THU-KHO** xác nhận nhận hàng và tạo phiếu nhập **PN-2604**.
10. **THU-KHO** lập biên bản kiểm tra **BBKT-2604**, xác nhận hàng hóa không có lỗi.
11. **DE-KH** lập hóa đơn mua hàng **VINV-2604**, chỉ khớp với mặt hàng HH-03 của đơn mua **PO-MP-2604** và phiếu nhập **PN-2604**.
12. **DP-MP** kết thúc quy trình, ghi nhận quy trình nhập kho hoàn tất thành công.

## Quy định áp dụng

- **KB-01**: Quy trình phê duyệt đơn hàng nhập kho yêu cầu **GD-MP (Giám đốc Công ty Minh Phát)** phê duyệt đơn hàng lớn. GD-MP là người duy nhất phê duyệt tất cả đơn hàng nhập kho, bất kể giá trị.
- **KB-02**: Quy trình phê duyệt đề nghị chi yêu cầu **TP-KT (Trưởng phòng Kế toán)** phê duyệt đề nghị chi với ngưỡng 50.000.000 VND trở xuống. Ngưỡng không giới hạn yêu cầu phê duyệt của TP-KT.
- **KB-03**: Quy định về thuế VAT áp dụng 10% cho đơn hàng mua hàng. Tổng giá trị đơn hàng được tính bằng tổng giá chưa VAT cộng với VAT 10%.
