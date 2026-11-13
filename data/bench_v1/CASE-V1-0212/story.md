# Mua máy in công nghiệp cho hệ thống phân phối

Công ty TNHH Phân phối Minh Anh, với 150 nhân sự và 30 cửa hàng trên cả nước, đã thực hiện đơn hàng mua 2 máy in công nghiệp theo hợp đồng số 2026-0413-MINHANH. Tuy nhiên, giá trên hóa đơn do nhà cung cấp gửi lên vượt quá 10% so với giá trong hợp đồng, tạo ra chênh lệch đáng kể. Kế toán phát hiện vấn đề và yêu cầu phê duyệt phần chênh lệch, nhưng Giám đốc từ chối do thiếu cơ sở minh bạch, dẫn đến việc giao dịch bị dừng lại và không thực hiện thanh toán.

## Diễn biến

1. **DP-ACQ** mở case "Mua 2 máy in công nghiệp theo hợp đồng số 2026-0413-MINHANH".
2. **DE-MH** tạo đơn mua hàng **PO-2026-0413**, đặt mua 2 máy in công nghiệp từ **NCC-01**, với đơn giá 60.000.000 VND/máy.
3. **NCC-01** gửi hóa đơn **VINV-2026-0413**, ghi giá 66.000.000 VND/máy.
4. **DE-KT** tạo phiếu nhập **GRN-2026-0413** khi nhận hàng.
5. **DE-KT** đối chiếu hóa đơn với đơn hàng và phiếu nhập, phát hiện chênh lệch 6.000.000 VND/máy.
6. **DE-KT** yêu cầu phê duyệt chênh lệch thông qua đề nghị chi **APR-2026-0413**.
7. **GD** xem xét và từ chối đề nghị chi do không đủ cơ sở minh bạch.
8. **DE-KT** không thực hiện thanh toán **PAY-2026-0413** do đề nghị chi bị từ chối.
9. **DP-ACQ** dừng quy trình với lý do: "Giám đốc từ chối phê duyệt chênh lệch giá, giao dịch dừng lại".

## Quy định áp dụng

- **KB-01**: Quy định về phê duyệt chênh lệch giá mua hàng: chênh lệch giá cho phép là 2%. Nếu chênh lệch vượt ngưỡng này, phải có phê duyệt theo loại "de_nghi_chi". Kế toán trưởng phê duyệt đến 20.000.000 VND, Giám đốc phê duyệt phần còn lại.
