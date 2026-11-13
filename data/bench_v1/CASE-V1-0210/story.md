# Mua phần mềm quản lý kho cho công ty công nghệ thông tin

Công ty Cổ phần Phần Mềm Việt (50 nhân viên, văn phòng tại TP. Hồ Chí Minh) đang tiến hành mua phần mềm quản lý kho từ nhà cung cấp NCC-01. Giao dịch có tổng giá trị 50.000.000đ, nhưng nhà cung cấp đã giao hàng trễ 10 ngày so với thời hạn trong hợp đồng. Điều này gây ra vấn đề trong quy trình thanh toán, vì theo hợp đồng, sẽ có bồi thường 10% giá trị giao dịch. Hệ thống phát hiện sự trễ hẹn và yêu cầu phê duyệt của cấp có thẩm quyền trước khi thanh toán.

## Diễn biến

1. **DP-01** Mở trường hợp mua phần mềm, tạo hồ sơ giao dịch với tiêu đề "Mua phần mềm quản lý kho từ NCC-01".
2. **DE-MH** Soạn đơn mua hàng (PO-001) cho 1 bộ phần mềm quản lý kho từ NCC-01.
3. **NCC-01** Giao hàng (van_don SHIP-001) vào ngày 30/03/2026, trễ 10 ngày so với ngày giao cam kết 20/03/2026.
4. **DE-MH** Kiểm tra ngày giao hàng và phát hiện trễ hẹn, ghi nhận 10 ngày trễ, ghi chú vấn đề.
5. **DE-MH** Ghi nhận hóa đơn mua hàng (INV-001) từ NCC-01, đối chiếu với đơn mua hàng PO-001 và vận đơn SHIP-001.
6. **DE-MH** Tính toán khoản bồi thường 10% (5.000.000đ) theo hợp đồng và tạo đề nghị chi (PAY-001) với tổng số tiền 49.500.000đ (45.000.000đ sau khi trừ bồi thường 5.000.000đ cộng thuế VAT 10% là 4.950.000đ).
7. **DE-MH** Yêu cầu phê duyệt đề nghị chi (APR-002) từ **KTT-01**.
8. **DP-01** Chờ **KTT-01** phê duyệt đề nghị chi APR-002.

## Quy định áp dụng

- **KB-001**: Quy trình phê duyệt thanh toán khi giao hàng trễ yêu cầu Kế toán trưởng (KTT-01) duyệt đề nghị chi (de_nghi_chi) với giá trị không vượt quá 50.000.000đ đồng và có sai lệch giá không quá 2%. Đề nghị chi phải đi kèm hóa đơn và vận đơn đã được đối chiếu.
- **de_nghi_chi**: Yêu cầu maker-checker, người duyệt là **KTT-01**.
- **tien_chi_toi_da**: 50.000.000đ đồng.
- **VAT_10**: Thuế giá trị gia tăng áp dụng 10%.
