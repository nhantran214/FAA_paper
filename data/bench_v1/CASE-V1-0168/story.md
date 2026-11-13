# Soạn thảo hợp đồng vận chuyển với đối tác thiếu hóa đơn

Công ty Vận Tải Minh Phát là doanh nghiệp có quy mô 30 nhân viên và 20 xe tải, hoạt động tại Hà Nội và các tỉnh đồng bằng sông Hồng. Trong trường hợp này, công ty đang tiến hành soạn thảo hợp đồng vận chuyển với đối tác AL. Tuy nhiên, hồ sơ thiếu hóa đơn GTGT 10% cho toàn bộ giá trị hợp đồng trị giá 100.000.000 VND. Việc thiếu hóa đơn khiến quy trình phê duyệt bị dừng lại, và pháp chế yêu cầu đối tác bổ sung chứng từ trước khi tiếp tục.

## Diễn biến

1. **Bộ phận điều phối** mở hồ sơ với tiêu đề "Soạn thảo hợp đồng vận chuyển với đối tác thiếu hóa đơn".
2. **Chuyên viên pháp lý PH** tạo hợp đồng **chứng từ** với đối tác **nhà cung cấp AL**, bao gồm 1 lần vận chuyển hàng hóa với đơn giá 100.000.000 VND và thuế suất 10%.
3. **Chuyên viên pháp lý PH** kiểm tra điều kiện có hóa đơn GTGT hay không, nhưng phát hiện vẫn thiếu hóa đơn, do đó ghi nhận lỗi.
4. **Chuyên viên pháp lý PH** gửi yêu cầu bổ sung hóa đơn GTGT cho đối tác **nhà cung cấp AL**.
5. **Chuyên viên pháp lý PH** gửi yêu cầu phê duyệt hợp đồng **chứng từ** với loại phê duyệt **hdpd_hop_dong**.
6. **Bộ phận điều phối** đợi phê duyệt từ **Giám đốc công ty NVM** cho yêu cầu **phiếu duyệt chứng từ**. Hiện tại, quy trình dừng lại cho đến khi nhận được hóa đơn từ đối tác.

## Quy định áp dụng

- **Quy trình phê duyệt hợp đồng với đối tác** yêu cầu phải có đầy đủ hóa đơn GTGT trước khi gửi lên cấp quản lý. Nếu thiếu hóa đơn, hệ thống sẽ dừng quy trình và yêu cầu đối tác bổ sung chứng từ sau khi hợp đồng được phê duyệt.
- **Quy định về hóa đơn GTGT trong hợp đồng** yêu cầu hợp đồng vận chuyển phải có hóa đơn GTGT 10% theo quy định hiện hành. Kế toán trưởng phê duyệt hợp đồng có giá trị dưới 100.000.000 VND, giám đốc phê duyệt hợp đồng có giá trị từ 100.000.000 VND trở lên.
- **hdpd_hop_dong**: Hợp đồng có giá trị dưới 100.000.000 VND được phê duyệt bởi kế toán trưởng, còn trên 100.000.000 VND thì do giám đốc phê duyệt.
- **han_muc_hoan_tat_ho_so**: Hạn mức hoàn tất hồ sơ là 100.000.000 VND.
- **VAT_10**: Áp dụng thuế suất 10% cho hóa đơn GTGT của hợp đồng vận chuyển, được lập sau khi giao dịch phát sinh.
