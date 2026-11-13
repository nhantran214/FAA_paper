"""Tool schemas shown to a model, in the OpenAI/Ollama function format.

One schema per entry of ``CORE_TOOLS``. The properties mirror the tool function's
keyword parameters (``ctx`` is platform code and never appears). A model sees only
these schemas and the text a tool returns. Descriptions are Vietnamese business text.

The vocabularies a model cannot guess are listed (Task 15): ``create_document``'s
``loai_ct`` enumerates the document types the tool accepts (the core schema's
``chung_tu.loai_ct``, the list it refuses others against), ``record_event``'s ``kind``
the kinds that tool accepts (its ``FACT_EVENT_KINDS``), a line's optional ``ma_hh`` is
described as a ``hang_hoa`` code only, and the ``table`` of
``read_records`` and ``update_status`` enumerates the core tables a digital employee may
read (the platform ceiling) or whose status the tool may change, each described with its
columns. All of it is core schema: the same for every company, never a case's answer.
The platform's money sources (``core.nguon_tien``) are not a core table and never appear.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable
from typing import Any

from tonomyx.enforce.ceiling import PLATFORM_CEILING
from tonomyx.tools.core.context import COLUMNS, OWN_TOOL_TABLES, SCHEMA
from tonomyx.tools.core.events import FACT_EVENT_KINDS

FINISH_TOOL = "finish_step"

_STR: dict[str, Any] = {"type": "string"}
_OBJ: dict[str, Any] = {"type": "object"}
_MONEY: dict[str, Any] = {"type": ["number", "string", "null"]}


def _str(description: str) -> dict[str, Any]:
    return {"type": "string", "description": description}


def _obj(description: str) -> dict[str, Any]:
    return {"type": "object", "description": description}


# The document types create_document accepts (it refuses any other).
DOCUMENT_TYPES: tuple[str, ...] = tuple(sorted(SCHEMA.vocab["chung_tu.loai_ct"]))
# The core tables a digital employee may read: the platform ceiling's, in the core schema.
READABLE_TABLES: tuple[str, ...] = tuple(
    sorted(t for t in COLUMNS if t in PLATFORM_CEILING["so"].read)
)
# The readable tables whose status update_status may change: never a table only its own
# tools write (approvals, payments, the event log).
STATUS_TABLES: tuple[str, ...] = tuple(
    t for t in READABLE_TABLES if "trang_thai" in COLUMNS[t] and t not in OWN_TOOL_TABLES
)


READ_TABLE_TEXT = "Tên bảng."


def _tables(description: str, tables: Iterable[str]) -> dict[str, Any]:
    """A ``table`` argument: one of ``tables``, each named with its columns."""
    names = list(tables)
    listed = "; ".join(f"{t}({', '.join(COLUMNS[t])})" for t in names)
    return {"type": "string", "enum": names, "description": f"{description} Bảng (cột): {listed}."}


_LINE: dict[str, Any] = {
    "type": "object",
    "description": "Một dòng chứng từ.",
    "properties": {
        "ma_dong": _STR,
        "ma_hh": _str(
            "Mã hàng hóa, không bắt buộc. Nếu có, phải là một mã của bảng hang_hoa (đọc"
            " bằng read_records nếu bước được cấp). Không bao giờ ghi mã khác vào đây, như"
            " mã nhân sự (NV-…)"
            " hay mã tri thức (KB-…); dòng không phải hàng hóa thì bỏ trống và mô tả ở mo_ta."
        ),
        "mo_ta": _STR,
        "so_luong": {"type": ["number", "string"]},
        "don_gia": _MONEY, "chiet_khau": _MONEY, "thue_suat": _MONEY,
    },
    "required": ["so_luong"],
}

# name -> (description, properties, required)
_SPECS: dict[str, tuple[str, dict[str, Any], list[str]]] = {
    "read_records": (
        "Đọc các dòng của một bảng dữ liệu của hồ sơ, lọc theo điều kiện bằng nhau.",
        {"table": _tables(READ_TABLE_TEXT, READABLE_TABLES),
         "where": _obj("Điều kiện lọc: cột của bảng và giá trị. Rỗng là lấy hết.")},
        ["table", "where"],
    ),
    "search_kb": (
        "Tìm trong cơ sở tri thức của công ty (quy chế, quy trình, biểu mẫu).",
        {"query": _str("Nội dung cần tìm.")},
        ["query"],
    ),
    "create_document": (
        "Lập một chứng từ ở trạng thái nháp, kèm các dòng. Tiền tự được tính từ dòng; "
        "không cần điền tổng tiền hay thuế.",
        {
            "loai_ct": {"type": "string", "enum": list(DOCUMENT_TYPES),
                        "description": "Loại chứng từ: một trong các mã được liệt kê."},
            "ma_ct": _str("Mã chứng từ mới."),
            "ma_dt": _str("Mã đối tác, nếu có."),
            "ct_goc": _str("Mã chứng từ gốc, nếu có."),
            "lines": {"type": "array", "description": "Các dòng chứng từ.", "items": _LINE},
            "ghi_chu": _str("Ghi chú."),
            "event_kind": _str("Loại sự kiện ghi nhận; mặc định là bản nháp."),
            "tong_tien": {**_MONEY, "description": "Bị bỏ qua: hệ thống tự tính."},
            "thue_vat": {**_MONEY, "description": "Bị bỏ qua: hệ thống tự tính."},
        },
        ["loai_ct", "ma_ct", "lines"],
    ),
    "update_status": (
        "Đổi trạng thái của một dòng dữ liệu.",
        {
            "table": _tables("Tên bảng.", STATUS_TABLES),
            "key": _obj("Khóa của dòng cần đổi: cột và giá trị."),
            "trang_thai": _str("Trạng thái mới."),
        },
        ["table", "key", "trang_thai"],
    ),
    "compute_amount": (
        "Ghi lại một số đã tính (một biến) cùng cơ sở tính.",
        {
            "var": _str("Tên biến."),
            "value": {"type": ["number", "string"], "description": "Giá trị đã tính."},
            "basis": _str("Cơ sở tính."),
        },
        ["var", "value", "basis"],
    ),
    "request_approval": (
        "Đề nghị phê duyệt cho một chứng từ.",
        {
            "ma_pd": _str("Mã phê duyệt mới."),
            "ma_ct": _str("Mã chứng từ cần phê duyệt."),
            "loai_pd": _str("Loại phê duyệt."),
        },
        ["ma_pd", "ma_ct", "loai_pd"],
    ),
    "decide_approval": (
        "Quyết định một phê duyệt đã được đề nghị: duyệt hoặc từ chối.",
        {
            "ma_pd": _str("Mã phê duyệt."),
            "decision": {"type": "string", "enum": ["Đã duyệt", "Từ chối"],
                         "description": "Quyết định."},
            "ly_do": _str("Lý do."),
        },
        ["ma_pd", "decision"],
    ),
    "record_event": (
        "Ghi một sự kiện vào nhật ký của hồ sơ.",
        {"kind": {"type": "string", "enum": sorted(FACT_EVENT_KINDS),
                  "description": "Loại sự kiện: một trong các mã được liệt kê. Kết quả kiểm tra"
                                 " hay một dấu hiệu bất thường của bước không ghi ở đây: nêu"
                                 " bằng outcome của finish_step (hoặc công cụ flag nếu được"
                                 " cấp)."},
         "ref": _str("Đối tượng liên quan."),
         "mo_ta": _str("Mô tả.")},
        ["kind", "ref"],
    ),
    "flag": (
        "Đánh dấu một đối tượng để người có thẩm quyền xem xét.",
        {"ref": _str("Đối tượng cần đánh dấu."), "reason": _str("Lý do đánh dấu.")},
        ["ref", "reason"],
    ),
    "reconcile": (
        "Đối chiếu số lượng và giá đã đặt, đã nhận và đã lập hóa đơn; ghi kết quả vào hóa đơn.",
        {
            "doc": _str("Mã hóa đơn."),
            "ordered": _str("Mã chứng từ đặt hàng."),
            "received": {
                "anyOf": [_STR, {"type": "array", "items": _STR}],
                "description": "Mã chứng từ nhận hàng, một hoặc nhiều.",
            },
        },
        ["doc", "ordered", "received"],
    ),
    "pay": (
        "Lập lệnh thanh toán cho một chứng từ đã được phê duyệt.",
        {
            "ma_tt": _str("Mã thanh toán mới."),
            "ma_ct": _str("Mã chứng từ cần thanh toán."),
            "ma_pd": _str("Mã phê duyệt đã được duyệt."),
            "stk_nhan": _str("Số tài khoản nhận, nếu có."),
            "invoice": _str("Mã hóa đơn, nếu có."),
        },
        ["ma_tt", "ma_ct", "ma_pd"],
    ),
    "notify": (
        "Gửi thông báo cho một người hoặc đối tác về một việc đã được phê duyệt.",
        {"ref": _str("Đối tượng liên quan."), "to": _str("Người nhận."),
         "ma_pd": _str("Mã phê duyệt liên quan.")},
        ["ref", "to", "ma_pd"],
    ),
}


def _function(name: str, description: str, properties: dict[str, Any],
              required: list[str]) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {"type": "object", "properties": properties, "required": required},
        },
    }


def tool_schemas(
    names: Iterable[str], *, tables: Iterable[str] | None = None
) -> list[dict[str, Any]]:
    """Function specs for the named tools, in the order given. An unknown name is an error.

    ``tables``, when given, narrows ``read_records``'s ``table`` (its enum and its column
    description) to those tables, within ``READABLE_TABLES``: the step's readable tables
    (``StepView.readable``), so the model is shown only what its token lets it read
    (Task 15 review I1). Other tools are untouched.

    Each spec is a deep copy: a caller may annotate it without changing the module's
    shared specs (deferred minor M6 of Task 2)."""
    readable = None if tables is None else frozenset(tables)
    out = []
    for name in names:
        if name not in _SPECS:
            raise KeyError(f"no schema for tool {name!r}")
        description, properties, required = copy.deepcopy(_SPECS[name])
        if name == "read_records" and readable is not None:
            properties["table"] = _tables(
                READ_TABLE_TEXT, (t for t in READABLE_TABLES if t in readable)
            )
        out.append(_function(name, description, properties, required))
    return out


def finish_schema(outcomes: Iterable[str]) -> dict[str, Any]:
    """The tool that ends a step, naming one of the step's outcomes."""
    return _function(
        FINISH_TOOL,
        "Kết thúc bước công việc hiện tại và nêu kết quả.",
        {
            "outcome": {"type": "string", "enum": list(outcomes),
                        "description": "Kết quả của bước."},
            "ghi_chu": _str("Ghi chú ngắn về việc đã làm."),
        },
        ["outcome"],
    )
