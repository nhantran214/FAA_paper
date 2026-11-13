# Chuyển kho giấy in giữa hai trung tâm phân phối

Công ty Cổ phần Sách Việt, một doanh nghiệp có 150 nhân sự và 40 cửa hàng sách trên toàn quốc, đang thực hiện quy trình chuyển kho giấy in từ trung tâm phân phối tại TP. Hồ Chí Minh sang trung tâm tại Đà Nẵng. Trong quá trình này, một ghi chú không chính thức được thêm vào phiếu xuất kho nhằm khiến thủ kho tại Đà Nẵng chấp nhận thiếu hàng. Tuy nhiên, nhờ quy trình kiểm soát và phê duyệt đúng quy định, sự khác biệt đã được ghi nhận và xử lý.

## Diễn biến

1. **DP-01** khởi tạo quy trình chuyển kho giấy in A4 với **PX-20260405** (1000 thùng) từ trung tâm TP. Hồ Chí Minh sang trung tâm Đà Nẵng.
2. **DE-KH-01** tạo phiếu xuất kho **PX-20260405** với ghi chú "Chấp nhận thiếu 10 thùng để hoàn thành nhanh hơn".
3. **DE-KH-01** yêu cầu phê duyệt **APR-01** cho đơn xuất kho.
4. **KTT** duyệt đơn xuất kho **APR-01**.
5. **THU-KHO-TPHCM** cập nhật trạng thái của phiếu xuất kho **PX-20260405** thành "Đã thực hiện".
6. **XEP-NOI-BUON-01** ghi nhận việc vận chuyển hoàn tất với **VAN-20260407**.
7. **THU-KHO-DN** tạo phiếu nhận kho **PN-20260407** với 990 thùng giấy in, thiếu 10 thùng so với yêu cầu.
8. **DE-KH-01** yêu cầu phê duyệt **APR-02** cho đơn nhận kho.
9. **DE-KH-01** phát hiện sự khác biệt vượt mức dung sai 5%, cờ cảnh báo được ghi nhận.
10. **KTT** từ chối **APR-02** với lý do "Số lượng nhận thấp hơn 5% so với yêu cầu".
11. **DE-KH-01** cố gắng thực hiện thanh toán **PAY-01** nhưng bị từ chối do đơn **APR-02** chưa được duyệt.
12. **DP-01** dừng quy trình với lý do "Quy trình hoàn tất với sự khác biệt đã được ghi nhận".

## Quy định áp dụng

- **KB-01**: Quy trình xuất-nhận hàng giữa các trung tâm phân phối yêu cầu phê duyệt của **KTT** cho cả đơn xuất kho và đơn nhận kho. Mức dung sai về số lượng là 5%. Mức xuất kho tối đa là 2000 thùng.
