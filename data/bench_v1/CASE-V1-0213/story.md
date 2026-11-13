# Điều chuyển máy tính bị hư giữa hai cửa hàng

Tại Công ty Cổ phần Chuỗi Cửa Hàng Mê Kích (Mê Kích Retail), một máy tính bàn (mã tài sản TSCD-1204) đang được điều chuyển từ cửa hàng số 12 (Hà Nội) sang cửa hàng số 17 (TP.HCM) để tiếp tục sử dụng. Tuy nhiên, trong quá trình kiểm tra, thủ kho tại cửa hàng số 17 phát hiện tài sản bị hư hỏng màn hình và yêu cầu hủy tài sản. Việc xử lý hiện đang chờ phê duyệt của Giám đốc Tài sản.

## Diễn biến

1. **DP-01** tạo hồ sơ "Điều chuyển máy tính bị hư giữa hai cửa hàng" để khởi động quy trình xử lý tài sản cố định.
2. **DE-TSCD-01** tạo biên bản kiểm tra (BB-001) cho tài sản TSCD-1204 với đơn giá 35.000.000 VND và kiểm tra tình trạng hư hỏng.
3. **DE-TSCD-01** phát hiện tài sản bị hư hỏng và ghi nhận cờ (flag) lý do: "Tài sản bị hư hỏng màn hình cần xử lý theo quy trình hủy tài sản".
4. **DE-TSCD-01** gửi yêu cầu phê duyệt xử lý tài sản bị hư hỏng (APR-001) lên **GD-TSCD**.
5. **DP-01** đang chờ **GD-TSCD** phê duyệt yêu cầu APR-001. Quy trình dừng lại ở đây và chưa có hành động nào tiếp theo.

## Quy định áp dụng

- **KB-01**: Quy trình xử lý tài sản cố định bị hư hỏng yêu cầu phê duyệt từ **GD-TSCD** (Giám đốc Tài sản) khi phát hiện hư hỏng không thể sửa chữa.
