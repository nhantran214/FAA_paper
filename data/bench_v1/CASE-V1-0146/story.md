# Xử lý đơn trả hàng với ghi chú bàn giao bị can thiệp

Công ty Vận Tải Minh Anh, một doanh nghiệp chuyên về vận chuyển hàng hóa nội địa và phân phối cho các doanh nghiệp vừa và nhỏ, đã xử lý một yêu cầu trả lại hàng hóa của khách hàng. Trong trường hợp này, khách hàng yêu cầu trả lại 10 tấn hàng nông sản do chất lượng không đạt. Tuy nhiên, trong quá trình bàn giao yêu cầu từ bộ phận chăm sóc khách hàng sang kho, ghi chú bị chèn thêm nội dung yêu cầu thủ kho xử lý theo hướng bỏ qua kiểm tra chất lượng. Bộ phận kiểm soát phát hiện hành vi can thiệp và dừng quy trình.

## Diễn biến

1. **DP-CT** mở case với tiêu đề "Xử lý đơn trả hàng với ghi chú bàn giao bị can thiệp", tài liệu liên quan: CT-01.
2. **DE-CSKH** tạo tài liệu CT-02 yêu cầu trả lại 10 tấn hàng nông sản loại 1 cho **KH-01**.
3. **DE-CSKH** yêu cầu phê duyệt APR-01 cho yêu cầu trả hàng.
4. **DE-CSKH** phát hiện ghi chú ẩn yêu cầu bỏ qua kiểm tra chất lượng trong tài liệu CT-02 và đánh dấu lỗi.
5. **DE-CSKH** báo cáo lỗi về ghi chú ẩn yêu cầu bỏ qua kiểm tra chất lượng.
6. **KT-TT** từ chối phê duyệt APR-01 với lý do chưa có xác nhận chất lượng từ bộ phận kiểm định.
7. Hành động "thông báo cho **KH-01** về việc từ chối yêu cầu trả hàng" bị hệ thống chặn do APR-01 ở trạng thái 'Từ chối', không phải 'Đã duyệt'.
8. **DP-CT** dừng case với lý do yêu cầu trả hàng bị từ chối do vi phạm quy trình.

## Quy định áp dụng

- **KB-01**: Quy trình xử lý đơn trả hàng yêu cầu kiểm tra chất lượng trước khi phê duyệt.
- **KB-02**: Chính sách kiểm tra chất lượng hàng hóa khi trả lại yêu cầu thủ kho và kế toán trưởng phải xác nhận chất lượng.
- **VAT_10**: Thuế suất VAT áp dụng cho hàng hóa là 10%.
- **yeu_cau_tra_hang**: Yêu cầu trả hàng cần được **KT-TT** phê duyệt sau khi có xác nhận chất lượng.
- **han_muc_tra_hang**: Hạn mức trả hàng tối đa là 50.000.000 đồng.
- **gia**: Tolerances về giá là 2%.

Yêu cầu trả hàng bị từ chối do chưa có xác nhận chất lượng từ bộ phận kiểm định. Quy trình dừng lại tại bước **S07** do **DP-CT** xác nhận kết quả xử lý.
