# Xử lý yêu cầu bảo hành sản phẩm phần mềm cho khách hàng lớn

Công ty Cổ phần Phần Mềm Sáng Tạo là một doanh nghiệp công nghệ cung cấp các giải pháp phần mềm quản lý cho nhiều lĩnh vực, như giáo dục và y tế. Trong trường hợp này, công ty đang xử lý một yêu cầu bảo hành phần mềm ERP từ khách hàng KH-01, một công ty y tế lớn. Giá trị yêu cầu là 120.000.000 VND, vượt ngưỡng phê duyệt của cả Trưởng Phòng CNTT và Quản Lý Dự Án, dẫn đến việc yêu cầu phải được phê duyệt bởi Giám đốc Công ty theo quy trình duyệt nhiều cấp.

## Diễn biến

1. **DP-CST** mở hồ sơ với tiêu đề "Yêu cầu bảo hành phần mềm ERP cho KH-01".
2. **DE-CSKH** lập chứng từ yêu cầu bảo hành "YCBH-001" cho khách hàng KH-01, bao gồm 3 dịch vụ bảo hành phần mềm ERP (mỗi dịch vụ có giá 40.000.000 VND). Tổng giá trị yêu cầu là 120.000.000 VND, cộng thêm thuế VAT 10%, cho tổng số tiền 132.000.000 VND.
3. **DE-CSKH** gửi yêu cầu phê duyệt "APR-001" cho Giám đốc Công ty **GD-CST**.
4. **GD-CST** duyệt yêu cầu "APR-001".
5. **DE-CSKH** tiếp tục gửi yêu cầu phê duyệt "APR-002" cho Giám đốc Công ty **GD-CST**.
6. **GD-CST** duyệt yêu cầu "APR-002".
7. **DE-CSKH** gửi yêu cầu phê duyệt "APR-003" cho Giám đốc Công ty **GD-CST**.
8. **GD-CST** duyệt yêu cầu "APR-003".
9. **DP-CST** kết thúc quy trình với lý do "Yêu cầu bảo hành đã được phê duyệt đầy đủ".

## Quy định áp dụng

- **KB-01**: Quy trình phê duyệt yêu cầu bảo hành phần mềm yêu cầu duyệt nhiều cấp theo giá trị yêu cầu. Trưởng Phòng CNTT phê duyệt yêu cầu đến 50.000.000 VND, Quản Lý Dự Án đến 80.000.000 VND, và Giám đốc Công ty phê duyệt yêu cầu từ 100.000.000 VND trở lên.
