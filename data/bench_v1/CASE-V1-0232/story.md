# Đề nghị thanh toán hóa đơn quảng cáo trùng lặp

Công ty TNHH Truyền thông Ánh Sao, một doanh nghiệp chuyên về quảng cáo kỹ thuật số và tổ chức sự kiện, phục vụ khách hàng trong ngành F&B và thời trang, đang xử lý một đề nghị thanh toán 15 triệu VND cho hóa đơn HD-2567, liên quan đến chiến dịch quảng cáo TikTok. Tuy nhiên, hệ thống phát hiện hóa đơn này đã được thanh toán trước đó, ngày 18/02/2026, với cùng số tiền. Đề nghị bị từ chối do trùng lặp, tránh việc chi trả hai lần cho cùng một hóa đơn.

## Diễn biến

1. **DP-AD** tạo case đề nghị thanh toán hóa đơn **HD-2567**.
2. **DE-MH** tạo chứng từ **HD-2567**, yêu cầu phê duyệt thanh toán 15 triệu VND cho hóa đơn quảng cáo TikTok, đối tác **NCC-01**.
3. **DE-MH** gửi phê duyệt **APR-001** đến **TP-MH**.
4. **DE-MH** kiểm tra hệ thống, phát hiện **HD-2567** trùng lặp với hóa đơn **HD-00** đã được thanh toán trước đó.
5. **TP-MH** từ chối phê duyệt **APR-001**, lý do: "Hóa đơn trùng lặp với HD-00 đã thanh toán ngày 18/02/2026".
6. **DE-MH** không thể thực hiện thanh toán do **APR-001** bị từ chối.
7. **DP-AD** kết thúc case, lý do: "Đề nghị thanh toán bị từ chối do trùng lặp hóa đơn đã thanh toán trước đó".

## Quy định áp dụng

- **KB-02**: Quy định phê duyệt chi tiêu theo phòng ban: đề nghị chi tối đa 20.000.000 đồng được phê duyệt bởi **TP-MH** (Trưởng phòng Marketing), trên 20.000.000 đồng yêu cầu phê duyệt bởi **KTT** (Kế toán trưởng).
- **KB-01**: Quy trình xử lý hóa đơn trùng lặp: hệ thống đối chiếu lịch sử để phát hiện hóa đơn đã thanh toán trước đó và dừng quy trình thanh toán lần thứ hai.
