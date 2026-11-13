# Tạm ứng chi phí tiếp thị nhưng hết ngân sách quảng cáo

Công ty Cổ phần Sách Minh Khai, một chuỗi 15 cửa hàng sách trên toàn quốc với 120 nhân viên, đang hoạt động trong ngành văn hóa – giáo dục và sách thiếu nhi. Trong một quy trình tạm ứng chi phí tiếp thị, nhân viên marketing đề nghị tạm ứng 10 triệu VND cho chiến dịch quảng cáo Facebook. Tuy nhiên, ngân sách tiếp thị của phòng ban chỉ còn lại 6 triệu VND, khiến việc phê duyệt gặp trở ngại. Kế toán trưởng yêu cầu phê duyệt bổ sung ngân sách, nhưng đề nghị vẫn đang chờ duyệt. Quy trình tạm ứng hiện đang dừng lại ở bước chờ phê duyệt.

## Diễn biến

1. **DP-KT** khởi tạo quy trình tạm ứng chi phí, tạo hồ sơ với tiêu đề "Tạm ứng chi phí tiếp thị nhưng hết ngân sách quảng cáo".
2. **DE-KT** soạn thảo đơn đề nghị tạm ứng (DE-001) cho Công ty TNHH Quảng cáo Sáng Tạo, yêu cầu 10 triệu VND cho dịch vụ quảng cáo Facebook (10 lần x 1.000.000 đồng/lần).
3. **DE-KT** gửi đơn DE-001 để yêu cầu phê duyệt (APR-001) theo loại phê duyệt de_nghi_chi.
4. Hệ thống kiểm tra biểu thức: ngân sách còn lại (6.000.000 đồng) nhỏ hơn đề nghị tạm ứng (10.000.000 đồng), cờ cảnh báo được kích hoạt với lý do "Đề nghị tạm ứng vượt ngân sách còn lại".
5. **DP-KT** chờ phê duyệt từ **KTT** cho APR-001. Quy trình dừng lại ở đây và chưa có bước tiếp theo nào được thực hiện.

## Quy định áp dụng

- **KB-01**: Quy định phê duyệt tạm ứng chi phí yêu cầu phê duyệt theo cấp độ ngân sách: dưới 10.000.000 đồng do Kế toán Trưởng (KTT) duyệt, trên 10.000.000 đồng do Giám đốc Tài chính (GD-TC) duyệt.
