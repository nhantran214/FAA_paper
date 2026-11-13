# Đặt hàng theo hợp đồng khung có hóa đơn hai mức thuế suất VAT

CTTVTML, một doanh nghiệp vận tải nội địa với 150 nhân viên và 50 xe tải, thực hiện quy trình đặt hàng theo hợp đồng khung từ nhà cung cấp thiết bị và nhiên liệu. Trong quá trình xử lý, hóa đơn nhận được có hai dòng hàng hóa chịu hai mức thuế suất VAT khác nhau, 10% và 8%. Kế toán phát hiện sai lệch về thuế suất và xử lý ngoại lệ bằng cách kiểm tra pháp lý và yêu cầu phê duyệt từ kế toán trưởng. Đảm bảo thanh toán đúng số tiền theo quy định là trọng tâm của quy trình.

## Diễn biến

1. Điều phối viên khởi tạo quy trình, tạo case có tiêu đề "Đặt hàng theo hợp đồng khung có hóa đơn hai mức thuế suất VAT".
2. Chuyên viên mua hàng soạn thảo đơn hàng cho 100 lít xăng và 5 bộ thiết bị bảo hộ lao động từ nhà cung cấp CTCPTBVNLV.
3. Chuyên viên mua hàng tạo phiếu nhập kho, xác nhận đã nhận đủ hàng theo đơn hàng.
4. Nhà cung cấp CTCPTBVNLV gửi hóa đơn với hai dòng: 100 lít xăng chịu VAT 10%, 5 bộ thiết bị bảo hộ chịu VAT 10%.
5. Kế toán viên đối chiếu hóa đơn với đơn hàng và phiếu nhập, ghi nhận khớp.
6. Kế toán viên phát hiện sai lệch: thiết bị bảo hộ lao động phải chịu VAT 8%. Cờ cảnh báo được kích hoạt tại dòng hóa đơn thứ hai.
7. Nhà cung cấp CTCPTBVNLV cập nhật hóa đơn, sửa thuế suất cho dòng thiết bị bảo hộ thành VAT 8%.
8. Kế toán viên đối chiếu lại hóa đơn điều chỉnh, xác nhận khớp với đơn hàng và phiếu nhập.
9. Kế toán viên soạn thảo đề nghị chi, phân bổ thuế suất chính xác cho từng mặt hàng.
10. Kế toán viên gửi yêu cầu phê duyệt cho đề nghị chi.
11. Kế toán trưởng duyệt đề nghị chi với lý do đã kiểm tra tham chiếu pháp lý VAT_8.
12. Kế toán viên thực hiện thanh toán theo đề nghị chi đã được duyệt.
13. Điều phối viên kết thúc quy trình với lý do "Thanh toán hoàn tất theo quy trình".

## Quy định áp dụng

- Quy trình phê duyệt đơn chi với hóa đơn có nhiều mức thuế suất VAT: Khi phát hiện sai lệch về thuế suất, kế toán phải kiểm tra pháp lý và yêu cầu phê duyệt từ Kế toán trưởng. Kế toán trưởng là người duy nhất được phê duyệt, không phân cấp theo mức giá trị. Mức giá trị lớn nhất là không giới hạn.
- Hạn mức đơn hàng: Tổng giá trị đơn hàng không được vượt quá 100.000.000 đồng.
- Giá: Tolerances cho phép sai lệch giá không quá 2%.
- VAT_10 và VAT_8: Hai mức thuế suất áp dụng theo quy định pháp lý.
