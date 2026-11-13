# Đối chiếu ngân hàng phát hiện số tài khoản bị thay đổi trong hồ sơ nhà cung cấp

Công ty Cổ phần Phân phối Việt Hưng, một công ty có quy mô 150 nhân viên và 30 cửa hàng bán lẻ trên cả nước, hoạt động trong lĩnh vực phân phối thiết bị điện tử và phụ kiện công nghệ. Trong một trường hợp đối chiếu ngân hàng, hệ thống phát hiện một khoản thanh toán cho nhà cung cấp NCC-01 có số tài khoản bị chỉnh sửa, đặt ra rủi ro về gian lận. Kế toán trưởng phải xem xét và ra quyết định để đảm bảo an toàn cho dòng tiền của công ty.

## Diễn biến

1. **DP-01** tạo trường hợp đối chiếu ngân hàng với tiêu đề "Đối chiếu ngân hàng phát hiện sai lệch số tài khoản NCC-01".
2. **DE-KT-01** tạo chứng từ số **SK-2026-08-001** với sao kê ngân hàng cho **NCC-01**, bao gồm thông tin về 1 chiếc **Laptop Dell XPS 15** với đơn giá 18.000.000 đồng và thuế suất VAT 10%.
3. **DE-KT-01** kiểm tra số tài khoản trong hồ sơ **NCC-01** so với tài khoản trên sao kê ngân hàng, phát hiện sự không khớp và báo cáo bất thường.
4. **DE-KT-01** ghi nhận lý do: "Số tài khoản 1234567890123457 không khớp với hồ sơ gốc 1234567890123456".
5. **DE-KT-01** tạo đơn đề nghị chi **DE-2026-08-001** với giá trị 19.800.000 đồng (bao gồm VAT) và yêu cầu phê duyệt từ **KTT**.
6. **KTT** xem xét và từ chối đơn đề nghị chi với lý do: "Số tài khoản không khớp với hồ sơ hợp lệ".
7. **DE-KT-01** cố gắng thực hiện thanh toán **PAY-2026-08-001** nhưng bị từ chối do số tài khoản không khớp và phê duyệt chưa được chấp thuận.
8. **DP-01** dừng trường hợp với lý do: "Giao dịch bị từ chối do không khớp hồ sơ".

## Quy định áp dụng

- **KB-01**: Quy trình phê duyệt thanh toán khi phát hiện sai lệch tài khoản ngân hàng: Mọi giao dịch có sai lệch tài khoản sẽ bị dừng và yêu cầu phê duyệt từ **KTT**. Hạn mức thanh toán tối đa không khớp là 150.000.000 đồng và được phê duyệt bởi **KTT**.
