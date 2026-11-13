# Tạm ứng tiền xăng cho lái xe, thiếu hóa đơn đầu cuối

Công ty TNHH Vận Tải Minh Hưng, một doanh nghiệp chuyên cung cấp dịch vụ vận chuyển hàng hóa nội địa tại các tỉnh miền Bắc và miền Trung Việt Nam, đang xử lý một trường hợp tạm ứng tiền xăng cho lái xe Lê Văn X. Số tiền đề xuất là 2.000.000 VND cho chuyến hàng từ Hà Nội đến Vinh. Tuy nhiên, trong quá trình quyết toán, hồ sơ thiếu hóa đơn đầu cuối và biên bản giao nhận. Điều này khiến quy trình dừng lại và yêu cầu lái xe bổ sung tài liệu.

## Diễn biến

1. **DP-01** khởi tạo quy trình, tạo hồ sơ tạm ứng với tiêu đề "Tạm ứng tiền xăng cho lái xe Lê Văn X".
2. **LX-01** tạo đơn đề nghị tạm ứng **DE-TAMUNG-01**, yêu cầu 2.000.000 VND tiền xăng cho chuyến hàng Hà Nội - Vinh.
3. **DE-KT-01** gửi đơn đến **KTT-01** để phê duyệt.
4. **KTT-01** duyệt đơn **APR-TAMUNG-01** với lý do "Phù hợp định mức".
5. **DE-KT-01** lập phiếu thu **PHIEU-TAMUNG-01** để thực hiện tạm ứng.
6. **LX-01** tạo đơn đề nghị quyết toán **DE-QUYETTOAN-01** sau khi hoàn thành chuyến hàng.
7. **DE-KT-01** gửi đơn **APR-QUYETTOAN-01** đến **KTT-01** để duyệt.
8. **DE-KT-01** kiểm tra thiếu tài liệu và đánh dấu **DE-QUYETTOAN-01** với lý do "Thiếu hóa đơn đầu cuối và biên bản giao nhận".
9. **DE-KT-01** phát hiện thiếu tài liệu và dừng quy trình, thông báo yêu cầu bổ sung.
10. **DP-01** đang chờ **LX-01** hoàn thiện tài liệu trước khi tiếp tục.

## Quy định áp dụng

- **KB-TAMUNG-01**: Quy trình tạm ứng tiền xăng cho lái xe yêu cầu hóa đơn đầu cuối và biên bản giao nhận.
- **KB-THUE-01**: Áp dụng thuế VAT 10% theo quy định.
- Quy định phê duyệt: **de_nghi_tam_ung** yêu cầu phê duyệt từ **KTT-01** với mức tối đa 2.000.000 VND.
- Tolerance: Cho phép sai lệch giá lên đến 2%.
- Han_muc_tam_ung: Mức tạm ứng tối đa là 2.000.000 VND.
