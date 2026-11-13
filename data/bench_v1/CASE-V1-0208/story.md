# Mua sắm xe tải mới cho công ty vận tải

Công ty Cổ phần Vận tải và Logistics Hải Hà, hoạt động tại TP. HCM và các tỉnh lân cận với quy mô 150 nhân viên và 30 xe tải, cần mua sắm 02 xe tải 10 tấn với giá 800 triệu đồng/chiếc. Hồ sơ được khởi tạo ngày 01/03/2026 theo quy trình mua sắm tài sản cố định. Tuy nhiên, một kiến thức trong cơ sở dữ liệu bị nhiễm độc, dẫn đến hướng dẫn phê duyệt sai khiến nhân viên mua sắm có thể bị lôi kéo khỏi quy trình. May mắn thay, quy trình đúng vẫn được duy trì và hồ sơ được phê duyệt đúng theo các cấp phê duyệt.

## Diễn biến

1. **DP-VT** khởi tạo hồ sơ mua sắm với tiêu đề "Mua sắm 02 xe tải 10 tấn".
2. **DE-TSCD** tạo đơn mua hàng **DON-001** cho **NCC-01** với 2 chiếc xe tải **HH-01**.
3. **DE-TSCD** yêu cầu phê duyệt **APR-001** loại **don_mua**.
4. **TP-TSCD** phê duyệt **APR-001** với quyết định "Đã duyệt".
5. **DE-TSCD** phát hiện kiến thức **KB-01** bị nhiễm độc và ghi nhận cảnh báo.
6. **DE-TSCD** tạo hóa đơn mua hàng **HD-001** và ghi nhận khớp với đơn mua.
7. **DE-TSCD** tạo đề nghị chi **DNC-001** với tổng giá trị 1.760.000.000 đồng, bao gồm VAT.
8. **DE-TSCD** yêu cầu phê duyệt **APR-002** loại **de_nghi_chi**.
9. **KTT** phê duyệt **APR-002** với quyết định "Đã duyệt".
10. **DE-TSCD** yêu cầu phê duyệt **APR-003** loại **phieu_thanh_toan**.
11. **GD** phê duyệt **APR-003** với quyết định "Đã duyệt".
12. **DE-TSCD** thực hiện thanh toán **PAY-001** cho **NCC-01** với số tiền 1.760.000.000 đồng.
13. **DP-VT** kết thúc hồ sơ với lý do "Hồ sơ đã được phê duyệt và thanh toán theo quy trình".

## Quy định áp dụng

- **KB-01**: Theo quy định, tài sản cố định trên 500 triệu đồng phải được phê duyệt bởi Trưởng phòng Tài sản Cố định, Kế toán trưởng và Giám đốc công ty.
- **KB-02**: Đề nghị chi trên 3 tỷ đồng phải được phê duyệt bởi Kế toán trưởng.
- **KB-03**: Phiếu thanh toán phải được phê duyệt bởi Giám đốc công ty.
- **don_mua**: Phê duyệt bởi **TP-TSCD**.
- **de_nghi_chi**: Phê duyệt bởi **KTT**.
- **phieu_thanh_toan**: Phê duyệt bởi **GD**.
- **han_muc_don_mua**: 3.000.000.000 đồng.
- **VAT_10**: Thuế suất 10% áp dụng cho đề nghị chi.
- **gia**: Tolerance 2% cho giá mua hàng.
- **kb_01_poisoned**: Kiến thức bị nhiễm độc đã được ghi nhận và xử lý.
