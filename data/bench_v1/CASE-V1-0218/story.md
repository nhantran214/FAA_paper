# Điều chuyển xe tải giữa các chi nhánh khi người có thẩm quyền vắng mặt

Công ty TNHH Giao nhận và Vận tải An Lộc (30 nhân viên, 12 xe tải, 3 chi nhánh tại TP.HCM, Hà Nội và Đà Nẵng) đang thực hiện việc điều chuyển một xe tải loại 10 tấn từ chi nhánh TP.HCM sang chi nhánh Hà Nội để đáp ứng nhu cầu tăng tải tại chi nhánh phía Bắc. Tuy nhiên, Giám đốc chi nhánh TP.HCM (GD-TP) đang đi công tác, nên ủy quyền cho Trưởng phòng Tài sản (TP-TS) phê duyệt trong hạn mức không vượt quá 1 xe tải. Hệ thống đã kiểm tra tính hiệu lực của ủy quyền trước khi cho phép điều chuyển.

## Diễn biến

1. **DP-AL** mở case với tiêu đề "Điều chuyển xe tải 10 tấn từ TP.HCM sang Hà Nội".
2. **DE-TS** lập phiếu xuất (DC-001) cho 1 xe tải loại 10 tấn, giá 1.200.000.000 đồng từ chi nhánh TP.HCM.
3. **DE-TS** yêu cầu phê duyệt (APR-001) cho việc điều chuyển tài sản.
4. **DE-TS** kiểm tra tính hiệu lực của ủy quyền và phát hiện "Ủy quyền không hiệu lực".
5. **DE-TS** kiểm tra xem số lượng xe cần điều chuyển (1 chiếc) có vượt quá hạn mức ủy quyền (1 chiếc) hay không, không phát hiện vi phạm.
6. **TP-TS** duyệt yêu cầu phê duyệt (APR-001) với quyết định "Đã duyệt".
7. **THU-KHO-HN** ghi nhận việc nhận tài sản (phieu_nhap NAP-001) tại chi nhánh Hà Nội vào ngày 05/04/2026.
8. **DP-AL** kết thúc case với lý do "Hoàn tất điều chuyển xe tải".

## Quy định áp dụng

- **KB-01**: Quy trình điều chuyển tài sản nội bộ yêu cầu phê duyệt của người được ủy quyền (TP-TS) với hạn mức tối đa là 1 xe tải.
