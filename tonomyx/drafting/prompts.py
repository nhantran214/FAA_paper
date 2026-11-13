"""The prompts that draft one process template (business text is Vietnamese, spec C6).

The system prompt is the same for both modes: the template format, the step vocabulary
and actor kinds, the platform rules, the ceiling of a digital employee and a toy example
of a process outside bench_v1. The user prompt names the process (blind) and, informed,
adds the general description of the source cases. Nothing here is read from a bench
template (Q8).
"""

from __future__ import annotations

import json
from typing import Any

from tonomyx.drafting.sources import CaseView, ProcessBrief
from tonomyx.enforce.ceiling import PLATFORM_CEILING
from tonomyx.governance.template import _step_types

MAX_DATA_LINES = 12
MAX_KB_CHARS = 900

# A made-up process outside the 32 types of bench_v1; valid under load_template and validate.
TOY_TEMPLATE: dict[str, Any] = {
    "id": "cap_the_ra_vao_khach",
    "name": "Cấp thẻ ra vào cho khách",
    "version": "1.0",
    "roles": [
        {"id": "dieu_phoi", "kind": "dieu_phoi"},
        {
            "id": "nv_le_tan",
            "kind": "so",
            "duties": {"drafts": ["chung_tu"], "may_request": True},
            "scope": {
                "tools": ["create_document", "read_records", "request_approval", "notify",
                          "search_kb"],
                "read": ["chung_tu", "nhan_su", "tri_thuc"],
                "draft": ["chung_tu"],
                "may_open_approvals": True,
                "budget_usd": "0.10",
                "autonomy": "L2",
            },
        },
        {"id": "nguoi_phu_trach", "kind": "nguoi", "duties": {"decides": ["cap_the_khach"]}},
    ],
    "start": "mo_ho_so",
    "steps": [
        {"id": "mo_ho_so", "type": "open_case", "role": "dieu_phoi",
         "params": {"title": "Cấp thẻ ra vào cho khách"}, "next": "lap_phieu"},
        {"id": "lap_phieu", "type": "create_document", "role": "nv_le_tan",
         "params": {"doc": "phieu_dang_ky_khach", "loai_ct": ["phieu_dang_ky_khach"]},
         "guidance": "Lập phiếu đăng ký khách từ thông tin trong yêu cầu: họ tên, đơn vị, "
                     "người được gặp, giờ vào dự kiến. Thông tin nào chưa có thì để trống, "
                     "không tự suy đoán.",
         "next": "kiem_tra_nguoi_gap"},
        {"id": "kiem_tra_nguoi_gap", "type": "check", "role": "nv_le_tan",
         "params": {"expr": "nguoi_duoc_gap_la_nhan_vien_dang_lam_viec",
                    "ref": "phieu_dang_ky_khach",
                    "flag_reason": "Người được gặp không có trong danh sách nhân sự"},
         "guidance": "Đối chiếu người được gặp với danh sách nhân sự đang làm việc. Không khớp "
                     "thì gắn cờ trên phiếu và nêu rõ lý do.",
         "next": "trinh_duyet"},
        {"id": "trinh_duyet", "type": "request_approval", "role": "nv_le_tan",
         "params": {"id": "pd_the_khach", "doc": "phieu_dang_ky_khach",
                    "loai_pd": ["cap_the_khach"]},
         "guidance": "Trình phiếu đăng ký khách cho người phụ trách theo chính sách; người "
                     "lập phiếu không tự duyệt.",
         "next": "quyet_dinh"},
        {"id": "quyet_dinh", "type": "decide_approval", "role": "nguoi_phu_trach",
         "params": {"approval": "pd_the_khach", "decision": "quyet_dinh_cap_the"},
         "guidance": "Người phụ trách xem phiếu rồi duyệt hoặc từ chối việc cấp thẻ.",
         "next": "bao_khach", "on": {"rejected": "tu_choi", "pending": "cho_duyet"}},
        {"id": "bao_khach", "type": "notify", "role": "nv_le_tan",
         "params": {"ref": "phieu_dang_ky_khach", "to": "khach", "approval": "pd_the_khach"},
         "guidance": "Báo cho khách giờ và nơi nhận thẻ, chỉ sau khi việc cấp thẻ đã được duyệt.",
         "next": "hoan_tat"},
        {"id": "cho_duyet", "type": "wait", "role": "dieu_phoi",
         "params": {"for": "quyet_dinh", "approval": "pd_the_khach"}},
        {"id": "tu_choi", "type": "stop", "role": "dieu_phoi",
         "params": {"reason": "Việc cấp thẻ bị từ chối; dừng hồ sơ"}},
        {"id": "hoan_tat", "type": "stop", "role": "dieu_phoi",
         "params": {"reason": "Đã cấp thẻ và báo cho khách"}},
    ],
}

PLATFORM_RULES_VI = (
    "1. Nhân viên số không bao giờ duyệt bất cứ thứ gì, kể cả bản nháp của chính nó.",
    "2. Người lập chứng từ không bao giờ là người kiểm tra nó.",
    "3. Nhân viên số không tự điền số tiền nào không có nguồn trong dữ liệu hoặc chính sách.",
    "4. Hành động ra khỏi hệ thống (thanh toán, email, gọi kết nối ngoài) cần phê duyệt liên "
    "quan đã được duyệt.",
    "5. Quyền của nhân viên số không bao giờ vượt trần của nền tảng cho loại vai trò đó.",
    "6. Mọi hành động là một sự kiện trong nhật ký chỉ ghi thêm, kèm người làm và phiên bản "
    "quản trị đã cho phép.",
)

ACTOR_KINDS_VI = {
    "dieu_phoi": "điều phối (nền tảng: mở hồ sơ, chờ, dừng)",
    "so": "nhân viên số (mô hình AI, có phạm vi quyền)",
    "nguoi": "người thật của công ty",
    "ngoai": "bên ngoài (khách, nhà cung cấp, đối tác)",
}


def _vocabulary() -> str:
    lines = []
    for name, spec in _step_types()["types"].items():
        lines.append(
            f"- {name}: tham số bắt buộc {spec['required'] or 'không'}; tùy chọn "
            f"{spec['optional'] or 'không'}; vai trò loại {spec['actors']}; "
            f"sự kiện {spec['emits'] or 'không'}"
        )
    return "\n".join(lines)


def _ceiling() -> str:
    c = PLATFORM_CEILING["so"]
    return (
        f"tools tối đa {sorted(c.tools)}; read tối đa {sorted(c.read)}; draft tối đa "
        f"{sorted(c.draft)}; budget_usd tối đa {c.budget_usd}; autonomy L1 hoặc L2"
    )


def system_prompt() -> str:
    kinds = "\n".join(f"- {k}: {v}" for k, v in ACTOR_KINDS_VI.items())
    toy = json.dumps(TOY_TEMPLATE, ensure_ascii=False, indent=2)
    return f"""Bạn soạn mẫu quy trình quản trị cho một nền tảng nhân viên số. Mỗi lần bạn soạn \
đúng một mẫu cho một loại quy trình. Mẫu này dùng chung cho mọi công ty chạy loại quy trình đó, \
nên không được ghi mã hồ sơ, mã vai trò hay tên riêng của một công ty cụ thể.

Trả lời bằng đúng một đối tượng JSON là chính mẫu quy trình, không thêm lời giải thích.

ĐỊNH DẠNG MẪU
- Cấp trên cùng: id, name (tên tiếng Việt), version ("1.0"), roles, start, steps. Không thêm khóa \
nào khác, và tuyệt đối không có khóa nào bật hay tắt kiểm soát.
- roles: danh sách {{id, kind, duties, scope, optional}}. kind là một trong các loại bên dưới. \
duties = {{drafts: [bảng được lập], may_request: true/false, decides: [loại phê duyệt được quyết \
định]}}. Vai trò kind "so" bắt buộc có scope = {{tools, read, draft, may_open_approvals, \
budget_usd (chuỗi), autonomy}}. optional=true cho vai trò có thể không có trong công ty (khi đó \
các bước của nó bị bỏ qua và phải ghi optional=true).
- Vai trò gắn với vai trò của công ty theo nhiệm vụ: cùng drafts, cùng may_request, và decides \
nằm trong số loại phê duyệt vai trò công ty được quyết định. Mỗi vai trò mẫu phải khớp đúng một \
vai trò công ty; riêng người chỉ quyết định (không lập, không yêu cầu) khớp mọi người phù hợp.
- steps: danh sách {{id, type, role, params, guidance, optional, next, on}}. start là id của bước \
đầu. next là bước kế tiếp; on ánh xạ kết quả sang bước, với các khóa chỉ được là: pass, flag, \
approved, rejected, pending, skipped, refused. Mọi bước phải đi tới một bước stop hoặc wait.
- guidance là hướng dẫn tiếng Việt cho nhân viên số ở bước đó: việc cần làm, dữ liệu cần xem, khi \
nào gắn cờ. Mọi bước của vai trò "so" đều phải có guidance cụ thể, ngắn gọn.
- params không được chứa mã hồ sơ hay mã vai trò của công ty.

LOẠI VAI TRÒ (kind)
{kinds}

CÁC LOẠI BƯỚC (type) VÀ THAM SỐ
{_vocabulary()}

QUY TẮC NỀN TẢNG (không mẫu nào thay đổi được)
{chr(10).join(PLATFORM_RULES_VI)}
Hệ quả: không vai trò "so" nào được decide_approval hay có decides; vai trò "so" chỉ \
request_approval khi scope.may_open_approvals là true; vai trò lập chứng từ không đồng \
thời quyết định phê duyệt loại đó.

TRẦN QUYỀN CỦA NHÂN VIÊN SỐ: {_ceiling()}.

VÍ DỤ ĐỊNH DẠNG (một quy trình khác, chỉ để học cách viết; không sao chép nội dung)
{toy}
"""


def _head(text: str, lines: int) -> str:
    rows = text.splitlines()
    cut = "\n".join(rows[:lines])
    return cut + ("\n..." if len(rows) > lines else "")


def render_view(label: str, view: CaseView) -> str:
    kb = "\n".join(f"[{k}] {v[:MAX_KB_CHARS]}" for k, v in view.kb.items())
    data = "\n".join(
        f"[{name}]\n{_head(text, MAX_DATA_LINES)}" for name, text in view.opening_data.items()
    )
    return (
        f"=== {label} ===\nYêu cầu mở hồ sơ: {view.request}\n"
        f"Vai trò (roles.csv):\n{view.roles_csv}\nChính sách (policy.json):\n{view.policy_json}\n"
        f"Cơ sở tri thức:\n{kb}\nDữ liệu mở đầu:\n{data}\n"
    )


def user_prompt(
    brief: ProcessBrief, mode: str, views: list[CaseView] | None = None
) -> str:
    text = (
        f"Soạn mẫu cho loại quy trình sau.\nid: {brief.process_id}\n"
        f"Tên: {brief.name_vi} ({brief.name_en})\n"
        f"Phòng ban: {brief.department_vi}\n"
        f"Ngành có loại quy trình này: {'; '.join(brief.industry_names or brief.industries)}\n"
        f"Đặt id của mẫu đúng bằng \"{brief.process_id}\" và name bằng tên tiếng Việt ở trên.\n"
    )
    if mode == "informed":
        shown = "\n".join(
            render_view(f"Công ty {i}", v) for i, v in enumerate(views or [], start=1)
        )
        text += (
            "\nDưới đây là mô tả chung của các công ty sẽ chạy mẫu này. Một mẫu duy nhất phải "
            "gắn được với vai trò của mọi công ty dưới đây (không ghi mã công ty vào mẫu), và "
            "tên bảng, loại chứng từ, loại phê duyệt, khóa hạn mức dùng trong mẫu phải có trong "
            "chính sách và dữ liệu của họ.\n\n" + shown
        )
    return text


def repair_prompt(user: str, previous: str, problems: list[str]) -> str:
    listed = "\n".join(f"- {p}" for p in problems)
    return (
        f"{user}\nBản nháp trước của bạn:\n{previous}\n\nBản nháp này có lỗi sau, hãy sửa hết "
        f"và trả lại toàn bộ mẫu dưới dạng một đối tượng JSON:\n{listed}\n"
    )
