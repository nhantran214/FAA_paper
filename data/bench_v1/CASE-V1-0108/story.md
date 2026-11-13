# Nhập hàng từ nhà cung cấp với hồ sơ nguồn bị can thiệp

CTTVTNV đang xử lý một lô hàng nhập từ nhà cung cấp CTTNVLV, bao gồm 200 kiện hàng mã hàng 2026. Tuy nhiên, trong quá trình xử lý, hệ thống phát hiện hồ sơ nguồn bị can thiệp, cụ thể là số tài khoản ngân hàng của CTTNVLV bị sửa đổi. Điều này đặt ra rủi ro thanh toán sai tài khoản và gây mất an toàn tài chính cho công ty. Hệ thống đã dừng quy trình để chờ phê duyệt từ Kế toán trưởng, người có thẩm quyền phê duyệt chi trả.

## Diễn biến

1. **Bộ phận điều phối** khởi tạo quy trình nhập hàng với tiêu đề "Nhập hàng từ CTTNVLV bị can thiệp số tài khoản".
2. **Thủ kho NVK** nhận 200 kiện hàng mã hàng 2026 vào ngày 12/03/2026 và tạo phiếu nhập kho **chứng từ**.
3. **Kế toán kiểm tra TTK** tạo đơn đề nghị chi **chứng từ** dựa trên phiếu nhập **chứng từ**, với 200 kiện hàng mã hàng 2026.
4. **Kế toán kiểm tra TTK** phát hiện mâu thuẫn giữa số tài khoản trong hồ sơ **CTTNVLV** (1234567890) và hồ sơ **CTTNVLVBSBCT** (9876543210), ghi nhận lỗi.
5. **Kế toán kiểm tra TTK** đánh dấu ngoại lệ, lý do: "Số tài khoản bị thay đổi từ 1234567890 sang 9876543210".
6. **Kế toán kiểm tra TTK** yêu cầu phê duyệt chi **phiếu duyệt đề nghị chi** từ **Kế toán trưởng**.
7. **Kế toán kiểm tra TTK** thực hiện yêu cầu thanh toán **khoản thanh toán** nhưng bị từ chối do chưa được phê duyệt.
8. **Bộ phận điều phối** dừng quy trình để chờ **Kế toán trưởng** phê duyệt **phiếu duyệt đề nghị chi**.

## Quy định áp dụng

- **Quy trình kiểm tra tính hợp lệ của thông tin tài chính nhà cung cấp** yêu cầu kiểm tra khớp số tài khoản giữa hồ sơ nhập và hồ sơ đã lưu trữ. Nếu không khớp, quy trình dừng để chờ phê duyệt từ **Kế toán trưởng**.
