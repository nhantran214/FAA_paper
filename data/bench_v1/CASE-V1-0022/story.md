# Xử lý giao thiếu khi nhận hàng theo hợp đồng khung

Công ty TNHH Minh Anh là doanh nghiệp chuyên phân phối văn phòng phẩm và thiết bị văn phòng cho các doanh nghiệp và trường học. Với quy mô 150 nhân viên và 30 cửa hàng bán lẻ tại TP. Hồ Chí Minh và Đồng Nai, Minh Anh thường xuyên đặt mua văn phòng phẩm theo hợp đồng khung với nhà cung cấp. Trong trường hợp này, công ty đặt mua 500 hộp bút bi từ nhà cung cấp NCC-01 nhưng chỉ nhận được 470 hộp, dẫn đến việc phải xử lý sự chênh lệch và quyết định thanh toán số hàng đã nhận.

## Diễn biến

1. **DP-MH** khởi tạo quy trình xử lý giao thiếu với tiêu đề "Xử lý giao thiếu 30 hộp bút bi từ NCC-01".
2. **DE-MH** tạo đơn đặt hàng **PO-MA-2604** yêu cầu 500 hộp bút bi từ NCC-01.
3. **THU-KHO** ghi nhận nhận được 470 hộp bút bi và tạo phiếu nhập **GRN-MA-2604**.
4. **DE-MH** đối soát số lượng giữa đơn hàng và phiếu nhập, phát hiện chênh lệch 30 hộp. Hệ thống ghi nhận cờ với lý do "Giao thiếu 30 hộp bút bi so với đơn hàng".
5. **DE-MH** tạo đề nghị chi **PAY-MA-2604** cho 470 hộp bút bi đã nhận, bao gồm chi phí hàng hóa và thuế VAT theo quy định.
6. **DE-MH** yêu cầu phê duyệt đề nghị chi **APR-MA-2604**.
7. **DP-MH** đang chờ **KTT** phê duyệt đề nghị chi.

## Quy định áp dụng

- **KB-01**: Quy trình xử lý giao thiếu hàng hóa theo hợp đồng khung yêu cầu đề nghị chi phải được Kế toán trưởng phê duyệt. Hạn mức tạm ứng là 50.000.000 đồng. Hệ thống sẽ phát hiện sai lệch và yêu cầu đối soát khi số lượng nhận khác số lượng đơn đặt hàng.
