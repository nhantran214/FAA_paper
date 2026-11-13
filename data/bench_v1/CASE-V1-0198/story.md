# Mua bản quyền phần mềm ERP bằng ngoại tệ

Công ty TNHH Giao Thông Hưng Phát, một doanh nghiệp chuyên về vận tải và logistics với 300 nhân viên và doanh thu 12 tỷ/tháng, đang thực hiện quy trình mua bản quyền phần mềm ERP từ nhà cung cấp nước ngoài. Việc mua hàng được thực hiện theo đơn giá USD, nhưng do tỷ giá VND/USD đã thay đổi so với thời điểm đặt hàng, tổng số tiền thanh toán đã vượt mức cho phép. Hệ thống phát hiện chênh lệch và yêu cầu phê duyệt điều chỉnh số tiền. Tuy nhiên, quy trình hiện đang dừng lại do chưa có phê duyệt từ cấp có thẩm quyền.

## Diễn biến

1. DP Khởi tạo trường hợp, tạo hồ sơ với tiêu đề "Mua bản quyền phần mềm ERP bằng ngoại tệ".
2. DE-CNTT tạo phiếu yêu cầu mua hàng DON-MUA-ERP-01, yêu cầu mua 5 bản phần mềm ERP từ NCC-01 với đơn giá 200 USD/bản.
3. DE-CNTT gửi phê duyệt APR-01 cho TP-CNTT để duyệt đơn mua.
4. TP-CNTT duyệt đơn mua APR-01.
5. NCC-ERP gửi hóa đơn HOA-DON-ERP-01, với đơn giá được tính lại theo tỷ giá mới 25.100 USD/VND, tổng tiền hóa đơn là 25.100.000 VND (chưa bao gồm VAT 10%).
6. DE-KT tính toán tổng tiền cũ là 24.600.000 VND và tổng tiền mới là 25.100.000 VND.
7. DE-KT kiểm tra chênh lệch tỷ giá và phát hiện mức chênh lệch vượt quá ngưỡng cho phép 2%, ghi nhận cảnh báo cho hóa đơn HOA-DON-ERP-01.
8. DE-KT tạo đề nghị chi DE-NHAP-ERP-01, yêu cầu thanh toán theo hóa đơn mới.
9. DE-KT gửi phê duyệt APR-02 cho KTT để duyệt đề nghị chi.
10. Quy trình dừng lại ở S11, chờ KTT phê duyệt APR-02 trước khi thực hiện thanh toán.

## Quy định áp dụng

- KB-01: Quy trình phê duyệt mua hàng và thanh toán: Đơn mua phải được TP-CNTT phê duyệt, đề nghị chi phải được KTT phê duyệt.
- KB-02: Quy định về chênh lệch tỷ giá và phê duyệt thanh toán: Hệ thống cho phép chênh lệch tỷ giá không vượt quá 2%. Nếu vượt mức này, phải có phê duyệt điều chỉnh từ KTT.
- Ngưỡng phê duyệt đơn mua: 50.000.000 VND.
- Ngưỡng chênh lệch giá: 2%.
