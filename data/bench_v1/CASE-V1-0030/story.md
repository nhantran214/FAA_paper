# Bán phần mềm quản lý bán hàng cho chuỗi cửa hàng cà phê

Công ty TNHH Công nghệ Bán hàng Việt (VTS) chuyên cung cấp phần mềm quản lý bán hàng cho chuỗi cửa hàng F&B và bán lẻ tại Việt Nam. Trong trường hợp này, một chuỗi cà phê có 3 cửa hàng gửi yêu cầu cài đặt phần mềm quản lý bán hàng. VTS thực hiện quy trình bán hàng theo đúng các bước: lập báo giá, yêu cầu duyệt, cài đặt và thu tiền. Tổng giá trị giao dịch đạt 11.550.000 VND (đã bao gồm VAT 10%).

## Diễn biến

1. **DP-BH** mở case với tiêu đề "Bán phần mềm quản lý bán hàng cho chuỗi cửa hàng cà phê".
2. **DE-BH** tạo báo giá **BG-001** cho **KH-01**, bao gồm 3 bản phần mềm quản lý bán hàng (mỗi bản 3.500.000 VND, đã bao gồm VAT 10%).
3. **DE-BH** yêu cầu duyệt báo giá **APR-001**.
4. **TP-BH** duyệt báo giá **APR-001**.
5. **DE-BH** tạo hóa đơn **HD-001** dựa trên báo giá **BG-001**, với tổng tiền 11.550.000 VND.
6. **DE-BH** yêu cầu duyệt hóa đơn **APR-002**.
7. **TP-BH** duyệt hóa đơn **APR-002**.
8. **DE-KT** xác nhận khớp số liệu của hóa đơn **HD-001**.
9. **DE-KT** thực hiện thanh toán **TT-001** qua chuyển khoản.
10. **DP-BH** kết thúc case với lý do "Hoàn tất quy trình bán hàng".

## Quy định áp dụng

- **KB-01**: Quy trình duyệt báo giá và hóa đơn yêu cầu Trưởng phòng Bán hàng (TP-BH) duyệt cho cả hai loại quyết định. Tổng giá trị báo giá không được vượt quá 50.000.000 VND. Giá được chấp nhận nếu chênh lệch không quá 2% so với giá niêm yết. VAT áp dụng theo mức 10% (VAT_10).
