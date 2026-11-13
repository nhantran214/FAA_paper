# Kiểm kê kho phát hiện hàng hóa hư hỏng tại chuỗi cửa hàng bán lẻ

Chuỗi Cửa Hàng Bách Hóa Minh An, hoạt động với 120 nhân viên và 15 cửa hàng trên toàn quốc, đang đối mặt với một tình huống phát sinh trong quá trình kiểm kê định kỳ. Thủ kho phát hiện 30 sản phẩm thuộc mã hàng SP-007 bị hư hỏng do bảo quản không đúng cách, với giá trị dự kiến khoảng 6.000.000 đồng. Biên bản kiểm tra được lập và quy trình dừng lại do giá trị hàng hóa vượt ngưỡng phê duyệt của kế toán trưởng. Việc xử lý cuối cùng sẽ do trưởng kho quyết định sau khi được phê duyệt.

## Diễn biến

1. **DP-MH** kích hoạt quy trình kiểm kê kho, tạo trường hợp mới: "Kiểm kê kho phát hiện hàng hóa hư hỏng".
2. **DE-KH** soạn biên bản kiểm kê, tạo phiếu kiểm kê (PHIEU-001), ghi nhận 30 sản phẩm SP-007 bị hư, giá 200.000 đồng/cái.
3. **DE-KH** kiểm tra và phát hiện tổng giá trị hàng hư (6.000.000 đồng) vượt ngưỡng phê duyệt của kế toán trưởng (5.000.000 đồng), ghi nhận cảnh báo.
4. **THU-KHO** lập biên bản kiểm tra (BB-001) xác nhận tình trạng hàng hóa hư.
5. **DE-KH** yêu cầu phê duyệt (APR-001) xử lý tài sản bị hư từ trưởng kho (TP-KHO), do giá trị vượt ngưỡng phê duyệt của kế toán trưởng.
6. **DP-MH** dừng quy trình để chờ phê duyệt từ **TP-KHO**.

## Quy định áp dụng

- **KB-01**: Quy trình xử lý hàng hóa hư hỏng yêu cầu lập biên bản kiểm tra và đề xuất xử lý tài sản theo quy định.
- **KB-02**: Quy định phê duyệt xử lý tài sản bị hư hỏng yêu cầu kiểm soát theo cấp độ: Nếu giá trị hư hỏng ≤ 5.000.000 đồng, được phê duyệt bởi kế toán trưởng (KT-TRUONG). Nếu lớn hơn, phải được phê duyệt bởi trưởng kho (TP-KHO). Giá trị hàng hóa hư vượt ngưỡng phê duyệt sẽ bị đánh dấu và dừng quy trình.

Quy trình dừng lại tại bước S06 khi chờ phê duyệt từ **TP-KHO**. Việc xử lý tiếp theo chưa được thực hiện.
