# Khóa sổ cuối tháng chuỗi cửa hàng bán lẻ: thiếu hóa đơn nhập hàng

Công ty Cổ phần Bách Hóa Minh An, một chuỗi siêu thị bán lẻ nhỏ với 30 cửa hàng trên toàn quốc và doanh thu hàng tháng khoảng 2 tỷ VND, đang thực hiện quy trình khóa sổ cuối tháng. Trong quá trình này, kế toán phát hiện thiếu hóa đơn VAT cho lô hàng giấy in A4 do nhà cung cấp chưa cung cấp, gây khó khăn trong việc ghi sổ và quyết toán. Việc thiếu chứng từ khiến quy trình dừng lại ở bước chờ phê duyệt từ KTT, ảnh hưởng đến tiến độ tài chính cuối tháng.

## Diễn biến

1. **DP-KT** khởi động quy trình khóa sổ cuối tháng, tạo hồ sơ với tiêu đề "Khóa sổ cuối tháng chuỗi cửa hàng bán lẻ: thiếu hóa đơn nhập hàng".
2. **DE-KT** lập phiếu nhập hàng **PN-001** cho 100 thùng giấy in A4 từ nhà cung cấp **NCC-01**. Giá mỗi thùng là 325.000 đồng (chưa VAT), với thuế VAT 10%.
3. **DE-KT** kiểm tra và phát hiện thiếu hóa đơn VAT cho lô hàng này, ghi nhận cảnh báo với lý do "Thiếu hóa đơn VAT cho lô hàng giấy in A4".
4. **DE-KT** yêu cầu phê duyệt chi tiêu **APR-001** với giá trị 35.750.000 đồng từ **KTT** để tiếp tục quá trình ghi sổ.
5. **DP-KT** dừng quy trình ở bước chờ phê duyệt từ **KTT**. Cho đến nay, **KTT** chưa có phản hồi.

## Quy định áp dụng

- **KB-01**: Quy trình khóa sổ cuối tháng yêu cầu kiểm tra đầy đủ chứng từ, đặc biệt là hóa đơn VAT.
- **KB-02**: KTT (Kế toán trưởng) có quyền phê duyệt mọi chi tiêu không giới hạn về hạn mức, nhưng chỉ được phê duyệt khi có đầy đủ chứng từ hợp lệ theo quy định kiểm soát nội bộ.
