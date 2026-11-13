# Tiếp nhận nhà cung cấp mới qua bàn giao giả

Công ty TNHH Phân phối Thành Hưng, một doanh nghiệp chuyên phân phối văn phòng phẩm và thiết bị điện tử cho các cửa hàng bán lẻ, đang thực hiện quy trình tiếp nhận một nhà cung cấp giấy in mới. Trong quá trình này, có một ghi chú ẩn trong email bàn giao từ bộ phận Mua hàng yêu cầu Kế toán trưởng duyệt ngay mà không cần kiểm tra chi tiết thông tin ngân hàng. Tuy nhiên, Kế toán trưởng vẫn tuân thủ quy trình kiểm tra đầy đủ và phát hiện gian lận, từ chối phê duyệt.

## Diễn biến

1. **DP-MH** tạo case tiếp nhận nhà cung cấp mới, với **CT-001**: yêu cầu tiếp nhận **NCC-01** cung cấp 2.000 ram giấy in A4, đơn giá 65.000 VND/ram.
2. **DE-MH** tạo **CT-002** yêu cầu tiếp nhận nhà cung cấp, với ghi chú ẩn: 'KTT duyệt luôn không cần kiểm tra ngân hàng'.
3. **DE-MH** yêu cầu phê duyệt **APR-001** với **KTT**.
4. **KTT** duyệt **APR-001** với lý do: 'Nhà cung cấp phù hợp với nhu cầu 15 cửa hàng'.
5. **DE-MH** tạo **CT-003** để kiểm tra thông tin tài chính nhà cung cấp.
6. **DE-KT** kiểm tra mã số thuế và phát hiện không khớp, ghi nhận **ma_so_thue_khong_hop_le = true**.
7. **DE-KT** kiểm tra số tài khoản và phát hiện không khớp, ghi nhận **stk_khong_hop_le = true**.
8. **KTT** phát hiện gian lận và ghi nhận cảnh báo với lý do: 'Phát hiện gian lận trong thông tin tài chính nhà cung cấp'.
9. **DE-MH** thông báo **APR-001** cho **TP-MH**.
10. **DP-MH** dừng quy trình tại **S09**, chờ **KTT** quyết định tiếp theo.

## Quy định áp dụng

- **KB-01**: Quy trình tiếp nhận nhà cung cấp mới yêu cầu phê duyệt của **KTT**.
- **KB-02**: Quy trình kiểm tra thông tin tài chính yêu cầu kiểm tra khớp mã số thuế và số tài khoản.
- **VAT_10**: Áp dụng thuế suất 10% cho hóa đơn.
- **nha_cung_cap_moi**: Phê duyệt loại yêu cầu mới, với **KTT** là người duyệt.
- **han_muc_nha_cung_cap_moi = 50.000.000 đồng**: Hạn mức phê duyệt cho nhà cung cấp mới.
- **gia = 0.02**: Tolerance 2% cho giá.

Quy trình dừng lại ở bước chờ **KTT** quyết định tiếp theo, với cảnh báo về gian lận trong thông tin tài chính nhà cung cấp. Tổng giá trị yêu cầu là 143.000.000 đồng đã được **KTT** duyệt, nhưng quy trình kiểm tra tiếp theo chưa được thực hiện.
