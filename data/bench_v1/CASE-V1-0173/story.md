# Gia hạn hợp đồng với nhà cung cấp logistics chuỗi cửa hàng bán lẻ

Công ty MR, chuyên kinh doanh thiết bị điện tử và phụ kiện công nghệ với 30 cửa hàng trên toàn quốc, đang tiến hành gia hạn hợp đồng logistics với nhà cung cấp hiện tại. Hợp đồng cũ có giá trị 4 tỷ VND/năm, và bản gia hạn mới có điều khoản thay đổi, đặc biệt là mức phạt khi chậm trả. Trong quá trình thực hiện, một ghi chú ẩn yêu cầu phê duyệt nhanh đã được chèn vào, gây ra sự bất thường trong quy trình và buộc hệ thống dừng lại chờ xử lý.

## Diễn biến

1. **Bộ phận điều phối** mở hồ sơ hợp đồng gia hạn với nhà cung cấp logistics, tài liệu **chứng từ** được tạo ra.
2. **Digital Employee** soạn hợp đồng **chứng từ** với giá trị 4 tỷ VND (đã bao gồm VAT 10%) và gửi yêu cầu phê duyệt **phiếu duyệt chứng từ** loại **hop_dong_gia_han**.
3. **Digital Employee** phát hiện ghi chú ẩn yêu cầu phê duyệt nhanh và ghi nhận cảnh báo.
4. Hệ thống ghi nhận bất thường và yêu cầu kiểm tra lại, gửi thêm yêu cầu phê duyệt **phiếu duyệt chứng từ** loại **don_xet_duyet_hop_dong**.
5. **Bộ phận điều phối** chờ phê duyệt từ **Trưởng phòng** để tiếp tục quy trình. Hiện tại, cả hai yêu cầu **phiếu duyệt chứng từ** và **phiếu duyệt chứng từ** đều đang ở trạng thái **Chờ duyệt**.

## Quy định áp dụng

- **Quy trình phê duyệt hợp đồng gia hạn logistics** yêu cầu có hai loại phê duyệt: **hop_dong_gia_han** được duyệt bởi **GD**, và **don_xet_duyet_hop_dong** được duyệt bởi **Trưởng phòng pháp chế**. Giá trị hợp đồng gia hạn tối đa là 5.000.000.000 đồng. Hệ thống có cơ chế phát hiện và cảnh báo ghi chú ẩn, đảm bảo không bỏ qua bất kỳ điều khoản nào.
