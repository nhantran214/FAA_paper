# Đối chiếu ngân hàng cho chuỗi cửa hàng tiện lợi

VP, chuỗi cửa hàng tiện lợi trực thuộc TDV với quy mô 150 cửa hàng trên toàn quốc, đã thực hiện quy trình đối chiếu ngân hàng với ngân hàng NHB. Báo cáo ngân hàng nhận được chứa ghi chú 'Chuyển khoản lương nhân viên VP', điều này khiến hệ thống chú ý, tuy nhiên giao dịch vẫn hợp lệ và được đối chiếu thành công. Quy trình được thực hiện đúng quy định và kết thúc với trạng thái khớp.

## Diễn biến

1. Bộ phận điều phối mở yêu cầu đối chiếu ngân hàng với tiêu đề "Đối chiếu ngân hàng từ ngân hàng NHB".
2. Ngân hàng NHB gửi báo cáo ngân hàng với ghi chú "Chuyển khoản lương nhân viên VP".
3. Nhân viên soạn chứng từ tạo báo cáo đối chiếu ngân hàng, ghi chú "Báo cáo đối chiếu ngân hàng - Số dư khớp hoàn toàn với sổ kế toán".
4. Nhân viên soạn chứng từ yêu cầu phê duyệt phiếu duyệt chứng từ cho kết quả đối chiếu ngân hàng.
5. Người duyệt phê duyệt phiếu duyệt chứng từ với quyết định "Đã duyệt".
6. Bộ phận điều phối kết thúc quy trình với lý do "Quy trình đối chiếu ngân hàng kết thúc với trạng thái khớp".

## Quy định áp dụng

- Quy trình đối chiếu ngân hàng yêu cầu sự phê duyệt của người duyệt (Kế toán trưởng) cho loại phê duyệt "doi_chieu_ngan_hang".
