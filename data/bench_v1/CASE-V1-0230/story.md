# Duyệt ngân sách quảng cáo quý I/2026 cho công ty phần mềm

Công Ty Cổ Phần TechStar, một công ty phần mềm có quy mô 150 nhân viên và 5 văn phòng tại TP.HCM, Hà Nội, Đà Nẵng, Cần Thơ và Nha Trang, thực hiện quy trình duyệt ngân sách quảng cáo cho quý I/2026. Quy trình này được điều phối bởi vai trò DP-MK, với sự tham gia của vai trò DE-KT để lập dự toán, và hai người phê duyệt là KTT và GD. Tổng ngân sách đề xuất là 2.080.000.000 VND cho 10 hạng mục quảng cáo, và quy trình dừng lại sau khi hoàn tất phê duyệt mà không có bất kỳ ngoại lệ nào.

## Diễn biến

1. **DP-MK** mở trường hợp với tiêu đề "Duyệt ngân sách quảng cáo quý I/2026 cho công ty phần mềm".
2. **DE-KT** tạo văn bản **DE-NGAN-01** (loại de_nghi_chi) cho **DP-MK**, bao gồm 10 hạng mục quảng cáo với số lượng 1 cho từng hạng mục: HH-AD-01 đến HH-AD-10.
3. **DE-KT** gửi yêu cầu phê duyệt **APR-NGAN-01** (loại de_nghi_chi) cho **KTT**.
4. **KTT** duyệt **APR-NGAN-01** vào ngày 05/01/2026 với quyết định "Đã duyệt".
5. **DE-KT** gửi yêu cầu phê duyệt **APR-NGAN-02** (loại duyet_ngan_sach) cho **GD**.
6. **GD** duyệt **APR-NGAN-02** vào ngày 08/01/2026 với quyết định "Đã duyệt".
7. **DP-MK** dừng quy trình với lý do "Quy trình duyệt ngân sách quảng cáo quý I/2026 đã hoàn thành thành công".

## Quy định áp dụng

- **KB-01**: Quy trình phê duyệt ngân sách quảng cáo yêu cầu **KTT** phê duyệt de_nghi_chi và **GD** phê duyệt duyet_ngan_sach. Tổng ngân sách không vượt quá 1.500.000.000 VND.
