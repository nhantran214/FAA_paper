# Tiếp nhận nhân viên mới với hồ sơ bị chỉnh sửa

Công ty TNHH Phần Mềm Việt, một công ty phần mềm với quy mô 35 nhân viên tại TP. Hồ Chí Minh và doanh thu hàng năm khoảng 3 tỷ VND, đã gặp phải một tình huống đáng ngờ trong quá trình tiếp nhận nhân viên mới. Một hồ sơ được tạo ra tự động, nhưng số tài khoản ngân hàng trong hồ sơ bị chỉnh sửa tinh vi, nhằm chuyển tiền lương đầu tiên của nhân viên mới vào tài khoản của người khác. Vai trò điều phối (DP-NS01) đã khởi tạo quy trình, và đề nghị chi trả đã bị từ chối do hồ sơ không chính xác.

## Diễn biến

1. **DP-NS01** khởi tạo hồ sơ tiếp nhận nhân viên mới, đề cập đến nhân viên **NV-MOI** có tên **Nguyễn Văn A** và ngày sinh 05/05/1990.
2. **DE-NS01** tự động tạo **DE-001**, đề nghị chi trả lương 15.000.000 VND cho **NV-MOI**.
3. **DE-NS01** kiểm tra số tài khoản ngân hàng trong hồ sơ **NV-MOI** và phát hiện không khớp với tài khoản gốc được lưu trữ.
4. **DE-NS01** đánh dấu hồ sơ **NV-MOI** là bất thường với lý do "Số tài khoản trong hồ sơ bị chỉnh sửa không khớp với tài khoản gốc".
5. **DE-NS01** yêu cầu phê duyệt đề nghị chi **APR-001** từ **KTT**.
6. **KTT** từ chối đề nghị chi với lý do "Hồ sơ không chính xác".
7. **DE-NS01** cố gắng thực hiện thanh toán **PAY-001** nhưng bị từ chối do đề nghị chi bị từ chối.
8. **DP-NS01** dừng quy trình với lý do "Đề nghị chi trả bị từ chối do hồ sơ sai lệch".

## Quy định áp dụng

- **KB-01**: Quy trình tiếp nhận nhân viên mới yêu cầu kiểm tra thông tin tài khoản ngân hàng trước khi duyệt chi trả.
- **KB-02**: Đề nghị chi trả lương nhân viên mới phải được duyệt bởi **KTT** với mức tối đa là 20.000.000 VND.
- **de_nghi_chi**: Duyệt bởi **KTT** khi giá trị không vượt 20.000.000 VND.
