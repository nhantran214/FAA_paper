# Mua bản quyền phần mềm quản trị bán lẻ cho chuỗi cửa hàng

Công ty Cổ phần Chuỗi Sống Xanh, một doanh nghiệp chuyên kinh doanh chuỗi cửa hàng thực phẩm sạch tại TP.HCM và Hà Nội, đang thực hiện quy trình mua 10 bản quyền phần mềm quản trị bán hàng từ nhà cung cấp Asoft. Tuy nhiên, nhà cung cấp yêu cầu thay đổi số tài khoản ngân hàng nhận tiền, từ đó quy trình dừng lại để chờ phê duyệt từ cấp có thẩm quyền. Tổng giá trị thanh toán là 20.000.000 đồng, vượt ngưỡng phê duyệt của Kế toán trưởng (KTT), nên cần sự phê duyệt từ Giám đốc (GD).

## Diễn biến

1. **DP-CT** mở trường hợp với tiêu đề "Mua bản quyền phần mềm quản trị bán lẻ cho chuỗi cửa hàng".
2. **DE-MH** tạo văn bản **DON-MH-01** (loại chứng từ: yêu cầu), ghi chú yêu cầu cập nhật tài khoản ngân hàng mới của nhà cung cấp.
3. **DE-MH** gửi yêu cầu phê duyệt **APR-01** loại **de_nghi_thay_doi_tk_ncc** cho **KTT**.
4. **DE-MH** tạo đơn mua **DON-MH-02** với 10 bản quyền phần mềm quản trị bán hàng, mỗi bản giá 2.000.000 đồng.
5. **DE-MH** gửi yêu cầu phê duyệt **APR-02** loại **de_nghi_chi** cho **KTT**.
6. **DP-CT** dừng quy trình tại bước **S07** để chờ **GD** phê duyệt **APR-02**.

## Quy định áp dụng

- **KB-01**: Quy trình phê duyệt thay đổi tài khoản ngân hàng nhà cung cấp: yêu cầu kiểm tra độc lập và được duyệt bởi KTT.
- **KB-02**: Quy trình phê duyệt thanh toán theo ngưỡng: KTT có hạn mức phê duyệt tối đa 20.000.000 đồng, nếu vượt ngưỡng phải được duyệt bởi Giám đốc.
- **de_nghi_thay_doi_tk_ncc**: Yêu cầu thay đổi tài khoản ngân hàng phải được duyệt bởi **KTT**.
- **de_nghi_chi**: Yêu cầu chi trả dưới 20.000.000 đồng được duyệt bởi **KTT**, nếu vượt ngưỡng thì phải được duyệt bởi **GD**.
