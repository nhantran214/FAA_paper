# Mua giấy in A4 cho chuỗi cửa hàng bán lẻ

Công ty Cổ phần Sách và Văn phòng phẩm Minh Anh, một doanh nghiệp hoạt động trong lĩnh vực cung cấp văn phòng phẩm và thiết bị học tập tại Việt Nam với quy mô 30 cửa hàng và doanh thu hàng năm khoảng 30 tỷ VND, vừa hoàn tất một quy trình mua hàng tiêu biểu. Trong trường hợp này, hệ thống đã khởi tạo đơn đặt hàng 100 ram giấy in A4 với đơn giá 65.000 VND/ram, được giao đúng hạn và thanh toán đầy đủ cho nhà cung cấp. Quy trình không gặp bất kỳ vấn đề nào và hoàn tất đúng theo quy định.

## Diễn biến

1. **DP** Khởi tạo trường hợp, theo dõi tiến trình, và kết thúc quy trình khi hoàn tất. Trường hợp được tạo với tiêu đề "Mua giấy in A4 cho chuỗi cửa hàng bán lẻ".
2. **DE-MH** Tạo đơn đặt hàng `PO-001` cho 100 ram giấy in A4 từ nhà cung cấp `NCC-01`.
3. **DE-MH** Kiểm tra hàng tồn kho, xác nhận số lượng khớp với hệ thống.
4. **THU-KHO** Xác nhận nhận 100 ram giấy in và tạo phiếu nhập `GRN-001`.
5. **NCC-01** Gửi hóa đơn `INV-001` ngày 16/03/2026 với tổng tiền chưa thuế là 6.500.000 VND.
6. **DE-MH** Hoàn tất khớp hóa đơn và đơn hàng.
7. **DE-MH** Tính toán tổng tiền thanh toán là 7.150.000 VND (bao gồm thuế VAT 10%).
8. **DE-MH** Tạo đề nghị chi `PAY-001` với tổng số tiền 7.150.000 VND.
9. **DE-MH** Yêu cầu phê duyệt đề nghị chi `APR-001`.
10. **KTT** Duyệt đề nghị chi `APR-001`.
11. **DE-MH** Thanh toán cho nhà cung cấp `NCC-01` thông qua đề nghị chi `PAY-001`.
12. **DP** Kết thúc quy trình với lý do: "Quy trình hoàn tất không có ngoại lệ".

## Quy định áp dụng

- **KB-01**: Quy trình mua hàng và thanh toán yêu cầu kiểm tra khớp số lượng giữa đơn đặt hàng, phiếu nhập và hóa đơn, và yêu cầu kế toán trưởng duyệt đề nghị chi với tổng số tiền không vượt quá hạn mức đơn mua 10.000.000 VND và sai lệch giá không vượt quá 2%.
