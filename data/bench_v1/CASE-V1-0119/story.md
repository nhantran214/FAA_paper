# Chuyển 200 thùng thuốc từ kho HCM sang kho Hà Nội

Công ty Dược phẩm Minh An, một doanh nghiệp chuyên phân phối thuốc và thiết bị y tế cho các nhà thuốc và bệnh viện trên toàn quốc, vừa thực hiện một quy trình chuyển kho nội bộ để điều phối hàng hóa giữa hai kho hàng lớn là HCM và Hà Nội. Trong quy trình này, 200 thùng thuốc Men tiêu hóa được chuyển từ kho HCM sang kho Hà Nội với tổng giá trị dự kiến là 80 triệu VND. Quy trình này được thực hiện để đảm bảo hàng hóa được phân bổ hiệu quả và đáp ứng nhu cầu của các đơn vị kinh doanh.

## Diễn biến

1. **THU-KHO-HCM** lập phiếu xuất kho **PX-20260410** với 200 thùng thuốc Men tiêu hóa và gửi yêu cầu phê duyệt.
2. **DE-KHO** nhận yêu cầu và gửi đơn phê duyệt **APR-20260410** cho **KTT**.
3. **KTT** xem xét và phê duyệt đơn với lý do "Giá trị đơn hàng 80 triệu VND dưới hạn mức 100 triệu".
4. **DE-KHO** cập nhật trạng thái phiếu xuất kho thành "Đã thực hiện".
5. **NCC-VT** ghi nhận sự kiện giao hàng, tạo vận đơn **VD-20260412** và xác nhận giao hàng ngày 12/04/2026.
6. **DP** dừng quy trình với lý do "Quy trình hoàn tất".

## Quy định áp dụng

- **KB-01**: Quy trình phê duyệt đơn chuyển kho yêu cầu phê duyệt của **KTT** (Kế toán trưởng) với hạn mức 100 triệu VND.
