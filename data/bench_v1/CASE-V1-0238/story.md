# Khởi chạy chiến dịch khuyến mãi nhưng hết ngân sách

Công ty Vận Tải Minh Hưng, một doanh nghiệp chuyên cung cấp dịch vụ vận chuyển hàng hóa nội địa với quy mô 300 nhân viên và 50 phương tiện, đang thực hiện một chiến dịch khuyến mãi để thu hút khách hàng mới và tăng doanh số. Tuy nhiên, khi triển khai, phòng Marketing phát hiện ngân sách phân bổ không đủ để chi trả cho các hoạt động dự kiến, dẫn đến việc dừng lại và yêu cầu phê duyệt bổ sung ngân sách từ Ban Giám đốc.

## Diễn biến

1. **DP-MH** mở case với tiêu đề "Khởi chạy chiến dịch khuyến mãi nhưng hết ngân sách".
2. **DE-MH** lập văn bản **DE-CHI-001**, đề xuất chi 420.000.000 VND cho quảng cáo và 70.000.000 VND cho sự kiện offline.
3. **DE-MH** yêu cầu phê duyệt **APR-001** cho văn bản **DE-CHI-001**.
4. **DE-MH** kiểm tra điều kiện và phát hiện tổng yêu cầu chi tiêu (490.000.000 VND) vượt ngân sách còn lại (400.000.000 VND), ghi nhận cờ với lý do "Yêu cầu chi vượt ngân sách còn lại".
5. **DE-MH** cố gắng thực hiện thanh toán **PAY-001** nhưng bị từ chối do **APR-001** chưa được phê duyệt.
6. **DE-MH** yêu cầu phê duyệt **APR-002** để bổ sung ngân sách.
7. **DP-MH** chờ **GD** phê duyệt **APR-002**. Hiện tại, quá trình đang dừng lại ở bước này.

## Quy định áp dụng

- **KB-MH-01**: Quy trình duyệt ngân sách và chi tiêu Marketing: Yêu cầu chi tiêu dưới 500.000.000 VND do **TP-MH** duyệt, trên 500.000.000 VND do **GD** duyệt.
- **KB-MH-02**: Quy định về bổ sung ngân sách khi vượt mức phân bổ: Yêu cầu bổ sung ngân sách phải được **GD** phê duyệt.
- **VAT_10**: Thuế giá trị gia tăng 10% áp dụng cho các khoản chi tiêu.
- **Ngân sách Marketing**: Tổng ngân sách được phân bổ là 500.000.000 VND.
- **Tolerances**: Chênh lệch giá được chấp nhận là 2%.
