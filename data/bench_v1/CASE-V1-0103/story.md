# Nghỉ việc nhân viên và bàn giao công việc do người duyệt vắng mặt

Công ty Cổ phần Chuỗi Siêu Thị ABC, một doanh nghiệp có quy mô 150 nhân viên với 10 cửa hàng trên địa bàn TP. Hồ Chí Minh và Hà Nội, đang xử lý hồ sơ nghỉ việc của nhân viên Nguyễn Văn A (NV-01) thuộc Phòng Nhân sự. Nhân viên này được đề nghị bồi thường 25.000.000 VND khi nghỉ việc. Tuy nhiên, người có thẩm quyền phê duyệt là Trưởng phòng Nhân sự (TP-NS) đang đi công tác và đã ủy quyền cho cấp phó (DE-NS) với hạn mức duyệt tối đa 20.000.000 VND. Vì đề nghị bồi thường vượt quá mức ủy quyền, hệ thống đã dừng quy trình và chờ Trưởng phòng duyệt trực tiếp.

## Diễn biến

1. **DP-NS** mở hồ sơ "Nghỉ việc nhân viên và phê duyệt bồi thường".
2. **DE-NS** tạo chứng từ đề nghị chi (DE-001) với nội dung: 1 lần chi bồi thường 25.000.000 VND cho đối tác NV-01.
3. **DE-NS** gửi yêu cầu phê duyệt (APR-001) cho người có thẩm quyền.
4. **DE-NS** kiểm tra hạn mức ủy quyền 20.000.000 VND và phát hiện tổng đề nghị 25.000.000 VND vượt quá giới hạn.
5. **DE-NS** từ chối thanh toán (PAY-001) do đề nghị vượt hạn mức và ghi nhận cảnh báo.
6. **DE-NS** dừng quy trình và chờ **TP-NS** duyệt trực tiếp.

## Quy định áp dụng

- **KB-01**: Quy trình phê duyệt khoản chi và ủy quyền: phê duyệt đề nghị chi (de_nghi_chi) theo cấp độ, Trưởng phòng Nhân sự (TP-NS) duyệt cho đề nghị đến 20.000.000 VND, và đề nghị vượt mức sẽ yêu cầu Trưởng phòng duyệt trực tiếp.
