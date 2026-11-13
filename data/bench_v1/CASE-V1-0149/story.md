# Khách hàng trả hàng với giá trị vượt ngưỡng phê duyệt

Ngày 10/03/2026, CTCPPPMH nhận được yêu cầu trả lại 200 sản phẩm thiết bị văn phòng từ khách hàng CTTT. Giá trị từng sản phẩm là 10.000.000 đồng, tổng giá trị yêu cầu trả hàng là 2.200.000.000 đồng, vượt ngưỡng phê duyệt của Trưởng phòng Chăm sóc khách hàng (20.000.000 đồng). Vì vậy, đề xuất trả hàng phải được phê duyệt bởi hai cấp quản lý: Trưởng phòng Chăm sóc khách hàng và Giám đốc kinh doanh.

## Diễn biến

1. Digital Process Coordinator tạo ca "Khách hàng CTTT trả lại 200 sản phẩm thiết bị văn phòng".
2. Digital Employee Chăm sóc khách hàng tạo phiếu đổi trả chứng từ cho CTTT, bao gồm 200 sản phẩm (MIDNHLPMM) với tổng giá trị 2.200.000.000 đồng.
3. Digital Employee Chăm sóc khách hàng gửi yêu cầu phê duyệt phiếu duyệt chứng từ loại de_nghi_tra_hang đến Trưởng phòng Chăm sóc khách hàng.
4. Trưởng phòng Chăm sóc khách hàng duyệt phiếu duyệt chứng từ với quyết định "Đã duyệt".
5. Digital Employee Chăm sóc khách hàng gửi yêu cầu phê duyệt phiếu duyệt chứng từ loại de_nghi_tra_hang đến Giám đốc kinh doanh.
6. Giám đốc kinh doanh duyệt phiếu duyệt chứng từ với quyết định "Đã duyệt".
7. Digital Process Coordinator dừng ca với lý do "Cả hai cấp phê duyệt đã hoàn thành".

## Quy định áp dụng

- Quy trình xử lý đơn trả hàng vượt ngưỡng phê duyệt yêu cầu phê duyệt bởi hai cấp: Trưởng phòng Chăm sóc khách hàng (ngưỡng 20.000.000 đồng) và Giám đốc kinh doanh (không có ngưỡng giới hạn).
