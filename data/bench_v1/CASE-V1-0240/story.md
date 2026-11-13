# Tổ chức chiến dịch khuyến mãi cho phần mềm kế toán

Công ty TNHH Phần Mềm Tài Chính Việt, một doanh nghiệp phát triển phần mềm kế toán, CRM và ERP cho các doanh nghiệp vừa và nhỏ tại Việt Nam, đang lên kế hoạch tổ chức một chiến dịch khuyến mãi cho phần mềm kế toán mới nhất. Trong quá trình triển khai, một tài khoản ngân hàng của khách hàng KH-01 đã bị sửa đổi để dẫn tiền về một tài khoản không liên quan. Bộ phận marketing đã phát hiện và dừng quy trình trước khi có bất kỳ khoản thanh toán nào được thực hiện.

## Diễn biến

1. **DP-PM** khởi tạo hồ sơ "Tổ chức chiến dịch khuyến mãi phần mềm kế toán".
2. **DE-MH** tạo văn bản yêu cầu "KM-01", bao gồm 100 bản phần mềm kế toán, gửi phê duyệt ngân sách cho **TP-MH**.
3. **TP-MH** duyệt văn bản "KM-01" với lý do "Ngân sách trong giới hạn 30 triệu VND".
4. **DE-MH** kiểm tra số tài khoản ngân hàng của KH-01 và phát hiện sự không khớp giữa tài khoản nhận tiền và hồ sơ gốc.
5. **DE-MH** ghi nhận lỗi và đánh dấu văn bản "KM-01-1" do "Tài khoản ngân hàng bị sửa đổi, không khớp với hồ sơ gốc".
6. **DP-PM** dừng quy trình tại bước chờ phê duyệt và đang đợi **TP-MH** xử lý.

## Quy định áp dụng

- **KB-01**: Quy trình phê duyệt ngân sách cho chiến dịch khuyến mãi: Trưởng phòng marketing (TP-MH) là người duy nhất có quyền duyệt ngân sách khuyến mãi, với mức duyệt tối đa 30 triệu VND.
- **KB-02**: Kiểm tra thông tin tài khoản ngân hàng của khách hàng: Kế toán trưởng (KTT) phải kiểm tra tính hợp lệ của thông tin tài khoản ngân hàng trong hồ sơ trước khi phê duyệt.
