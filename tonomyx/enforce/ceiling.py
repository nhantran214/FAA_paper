"""Platform ceiling: the most a digital employee of each actor kind may ever be given (rule 5)."""
from __future__ import annotations

from decimal import Decimal

from tonomyx.governance.template import RoleScope

AUTONOMY_ORDER = ("L1", "L2")

PLATFORM_CEILING: dict[str, RoleScope] = {
    "so": RoleScope(
        tools=frozenset({"read_records", "create_document", "update_status", "request_approval",
                         "record_event", "flag", "reconcile", "compute_amount", "pay", "notify",
                         "search_kb"}),
        read=frozenset({"doi_tac", "hang_hoa", "nhan_su", "ngan_sach", "tri_thuc", "ho_so",
                        "chung_tu", "dong_ct", "phe_duyet", "thanh_toan", "su_kien"}),
        draft=frozenset({"chung_tu", "dong_ct", "thanh_toan"}),
        may_open_approvals=True,
        budget_usd=Decimal("1.00"),
        autonomy="L2"),
}
