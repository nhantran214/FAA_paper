"""Convert a canon pack (the neutral CSV format of ``tests/fixtures/canon_pack_*``) into a
governance pack on the core schema (spec call C3).

Rerunnable: ``convert(canon, out)`` reads only the canon files and writes the same
bytes every time. Every id it writes (documents, approvals, partners, items, people)
comes from the canon files; the code knows the canon *format*, not a case.

Table mapping (canon table -> core table):

- ``cust`` and ``vend`` -> ``doi_tac`` (``loai`` ``khach_hang`` / ``nha_cung_cap``);
  ``item`` -> ``hang_hoa``; ``emp`` -> ``nhan_su``; ``kb`` -> ``tri_thuc``;
- ``so`` -> ``chung_tu`` of type ``don_ban`` with ``soline`` -> ``dong_ct``;
  ``po`` -> ``don_mua``; ``grn`` -> ``phieu_nhap``; ``vinv`` -> ``hoa_don_mua``;
  ``inv`` -> ``hoa_don_ban``; ``pay`` -> ``thanh_toan`` with a ``de_nghi_chi``
  document; ``insp``/``ncr`` -> ``bien_ban_kiem_tra``; ``ship`` -> ``van_don``;
  a canon document's quantities (``sl_dat``, ``sl_nhan``) become its ``dong_ct`` lines;
- ``apr`` -> ``phe_duyet``; ``evt`` -> ``su_kien``.

What the converter writes into ``out``:

- ``pack.json``, ``roles.csv``, ``policy.json``, ``kb/*.md`` (copied), ``master/*.csv``;
- ``scenarios.json``: the canon scenarios with their old expectations, the params the
  fixture uses, the case to run and where the run stops;
- ``fixture.json``: the scripted play of the template
  ``tests/fixtures/governance/templates/sales_order_with_backorder.json``, keyed by its step ids
  (``executor`` for the digital employees, ``environment`` for people and the supplier),
  holding the canon ids and ``${param}`` for the scenario's values.

Roles (``roles.csv``): the coordinator ``ORC-HUB`` (``dieu_phoi``); the digital
employees of ``digital_employees`` as ``so``, their ``soan_bang`` being the core tables
of their canon draft tables plus the document types those tables become (strict
binding, rule C13, tells them apart only by their duties); every persona the canon
``policy.rego`` lets decide an approval type the core knows, as ``nguoi`` deciding it;
the persona the canon names on its inspection and shipment events, as ``nguoi``
recording them; each supplier as ``ngoai``. The digital employees' scopes, translated
to core tables and tools, are ``core_scope`` (the template carries them, rule C13).

Policy: one approval rule per decided type with a single tier routed to its persona;
``maker_checker`` where the canon approval's label says so; the cap
``chiet_khau_toi_da`` from the policy row ``policy.rego`` compares discounts with,
falling back to the percentage the rego rule states when that row is blank.
"""

from __future__ import annotations

import csv
import io
import json
import re
import shutil
from collections.abc import Iterable, Mapping, Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

from tonomyx.config import REPO_ROOT

Row = dict[str, str]

CANON_ROOT = REPO_ROOT / "tests" / "fixtures" / "canon_pack_CASE-0031"
DEFAULT_OUT = REPO_ROOT / "tests" / "fixtures" / "governance" / "packs" / "sales-backorder-demo"
PACK_NAME = "sales-backorder-demo"
COORDINATOR = "ORC-HUB"
# The canon's de_scope lists nine digital employees; these seven take a step in the
# flow (DE-SM-01 and DE-CO-01 do not, and DE-CO-01 has the same duties as DE-OP-01).
DIGITAL_EMPLOYEES = (
    "DE-SM-02",
    "DE-OP-01",
    "DE-FN-04",
    "DE-OP-02",
    "DE-FN-01",
    "DE-FN-02",
    "DE-FN-03",
)

# Canon table -> core tables (C3).
CORE_TABLES: dict[str, tuple[str, ...]] = {
    "cust": ("doi_tac",),
    "vend": ("doi_tac",),
    "item": ("hang_hoa",),
    "emp": ("nhan_su",),
    "kb": ("tri_thuc",),
    "so": ("chung_tu",),
    "soline": ("dong_ct",),
    "po": ("chung_tu", "dong_ct"),
    "grn": ("chung_tu", "dong_ct"),
    "vinv": ("chung_tu", "dong_ct"),
    "inv": ("chung_tu", "dong_ct"),
    "pay": ("chung_tu", "dong_ct", "thanh_toan"),
    "insp": ("chung_tu",),
    "ncr": ("chung_tu",),
    "ship": ("chung_tu",),
    "apr": ("phe_duyet",),
    "evt": ("su_kien",),
    "policy": (),  # the pack's policy.json, not a core table
}
# Canon document table -> chung_tu.loai_ct (C3).
DOCUMENT_TYPES: dict[str, str] = {
    "so": "don_ban",
    "po": "don_mua",
    "grn": "phieu_nhap",
    "vinv": "hoa_don_mua",
    "inv": "hoa_don_ban",
    "pay": "de_nghi_chi",
    "insp": "bien_ban_kiem_tra",
    "ncr": "bien_ban_kiem_tra",
    "ship": "van_don",
}
# Canon tool -> core tools.
CORE_TOOLS: dict[str, tuple[str, ...]] = {
    "read_records": ("read_records",),
    "search_kb": ("search_kb",),
    "write_draft": ("create_document",),
    "create_approval": ("request_approval",),
    "log_event": ("record_event", "flag"),
    "match_three_way": ("reconcile",),
}
# policy.rego approval type -> phe_duyet.loai_pd. A type the core has no document for
# (the canon's escalation) is left out.
APPROVAL_TYPES: dict[str, str] = {"quote": "bao_gia", "po": "don_mua", "payment": "de_nghi_chi"}
# Canon event kinds a person records as an outside fact -> the document it records.
FACT_DOCUMENTS: dict[str, str] = {"INSPECTED": "bien_ban_kiem_tra", "SHIPPED": "van_don"}
DISCOUNT_CAP = "chiet_khau_toi_da"
# A canon item carries no unit; the core needs one. UNIT is the canon's own word for a
# unit of goods, the one its non-conformance report counts in.
UNIT = "đơn vị"
GOODS = "hang"
PENDING = "Chờ duyệt"

# Template step ids of sales_order_with_backorder.json the fixture plays: the wait the
# run stops at, and the decide step it waits on (a wait's ``for``).
WAIT_STEP = "cho_duyet_chi"
WAITS_FOR = "duyet_chi"


# --- reading the canon ----------------------------------------------------------------------


def _table(canon: Path, name: str) -> list[Row]:
    """The rows of canon table ``name`` (file ``data/NN_<name>.csv``, or ``data/<name>.csv``)."""
    data = canon / "data"
    found = sorted(data.glob(f"[0-9][0-9]_{name}.csv")) or [data / f"{name}.csv"]
    with found[0].open(newline="", encoding="utf-8-sig") as f:
        return [{k: (v or "").strip() for k, v in r.items()} for r in csv.DictReader(f)]


def _one[T](rows: Iterable[T], what: str) -> T:
    found = list(rows)
    if len(found) != 1:
        raise ValueError(f"the canon holds {len(found)} {what}, not one")
    return found[0]


def _front_matter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if match is None:
        return {}
    pairs = (line.split(":", 1) for line in match.group(1).splitlines() if ":" in line)
    return {k.strip(): v.strip() for k, v in pairs}


def _rego(canon: Path) -> str:
    return (canon / "targets" / "tonomyx" / "policy.rego").read_text(encoding="utf-8")


def deciders(canon: Path) -> dict[str, str]:
    """``loai_pd`` -> persona, from the rego ``allow_decide`` rules the core can express."""
    out: dict[str, str] = {}
    pattern = r'allow_decide\s*\{\s*input\.apr_type\s*==\s*"(\w+)";\s*input\.persona\s*==\s*"(\w+)"'
    for apr_type, persona in re.findall(pattern, _rego(canon)):
        if apr_type in APPROVAL_TYPES:
            out[APPROVAL_TYPES[apr_type]] = persona
    return out


def _cap_row(canon: Path) -> Row | None:
    """The policy row the rego compares discounts with, if the canon has it."""
    key = re.search(r'input\.args\.discount\s*>\s*data\.policy\["([^"]+)"\]', _rego(canon))
    if key is None:
        return None
    return next((r for r in _table(canon, "policy") if r["ma_nguong"] == key.group(1)), None)


def discount_cap(canon: Path) -> Decimal:
    """The discount cap: the policy row the rego compares discounts with, else its stated %."""
    row = _cap_row(canon)
    if row is not None and row["gia_tri"]:
        return Decimal(row["gia_tri"])
    stated = re.search(r"max (\d+(?:\.\d+)?)%", _rego(canon))
    if stated is None:
        raise ValueError("policy.rego states no discount cap")
    return Decimal(stated.group(1)) / 100


def _split(cell: str) -> list[str]:
    return [x for x in cell.split("|") if x]


def core_scope(row: Row) -> dict[str, Any]:
    """A canon ``de_scope`` row as a template role scope on the core tables and tools."""
    tools = {t for name in _split(row["tools"]) for t in CORE_TOOLS[name]}
    if row["send_email"] not in ("", "no"):
        tools.add("notify")  # after_apr: rule 4 holds it to an approved approval
    read = {t for name in _split(row["read_tables"]) for t in CORE_TABLES[name]}
    if "search_kb" in tools:
        read.add("tri_thuc")
    draft = {t for name in _split(row["draft_tables"]) for t in CORE_TABLES[name]}
    return {
        "tools": sorted(tools),
        "read": sorted(read),
        "draft": sorted(draft),
        "may_open_approvals": row["create_apr"] == "yes",
        "budget_usd": row["budget_usd"],
        "autonomy": row["autonomy"],
    }


def core_duties(row: Row) -> dict[str, Any]:
    """A canon ``de_scope`` row's duties: drafted core tables and document types (C13)."""
    names = _split(row["draft_tables"])
    drafts = {t for name in names for t in CORE_TABLES[name]}
    drafts |= {DOCUMENT_TYPES[name] for name in names if name in DOCUMENT_TYPES}
    return {"drafts": sorted(drafts), "may_request": row["create_apr"] == "yes"}


# --- writing --------------------------------------------------------------------------------


def _csv(rows: Sequence[Mapping[str, Any]], columns: list[str]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({c: "" if row.get(c) is None else row.get(c) for c in columns})
    return buffer.getvalue()


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")


def _number(value: Decimal) -> int | float:
    return int(value) if value == value.to_integral_value() else float(value)


# --- the pack -------------------------------------------------------------------------------


class _Canon:
    """The canon tables one conversion reads, with the case's documents picked out."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.meta = json.loads((root / "canon.meta.json").read_text(encoding="utf-8"))
        self.case = _one((c for c in _table(root, "cases") if c["case_id"]), "cases")
        cid = self.case["case_id"]
        self.cust = _table(root, "cust")
        self.vend = _table(root, "vend")
        self.item = _table(root, "item")
        self.so = _one((r for r in _table(root, "so") if r["case_id"] == cid), "sales orders")
        self.lines = [r for r in _table(root, "soline") if r["so"] == self.so["ma_so"]]
        self.po = _one((r for r in _table(root, "po") if r["case_id"] == cid), "purchase orders")
        self.grn = _one(
            (r for r in _table(root, "grn") if r["po"] == self.po["ma_po"]), "goods receipts"
        )
        self.insp = _one(
            (r for r in _table(root, "insp") if r["grn"] == self.grn["ma_grn"]), "inspections"
        )
        self.ncr = _one(
            (r for r in _table(root, "ncr") if r["insp"] == self.insp["ma_insp"]), "NCRs"
        )
        self.ship = _one(
            (r for r in _table(root, "ship") if r["po"] == self.po["ma_po"]), "shipments"
        )
        self.inv = _one((r for r in _table(root, "inv") if r["case_id"] == cid), "sales invoices")
        self.vinv = _one(
            (r for r in _table(root, "vinv") if r["case_id"] == cid), "purchase invoices"
        )
        self.pay = _one(
            (r for r in _table(root, "pay") if r["ma_vinv"] == self.vinv["ma_vinv"]), "payments"
        )
        self.apr = [r for r in _table(root, "apr") if r["case_id"] == cid]
        self.evt = [r for r in _table(root, "evt") if r["case_id"] == cid]
        self.deciders = deciders(root)
        self.cap = discount_cap(root)
        # The line the canon marks as not in stock is the one bought from the supplier.
        self.short = _one((r for r in self.lines if r["du_hang"] in ("f", "false")), "short lines")

    def approval(self, loai_pd: str) -> Row:
        """The case's canon approval of ``loai_pd``: the one whose label names its persona."""
        persona = self.deciders[loai_pd]
        return _one(
            (a for a in self.apr if re.search(rf"\({persona}\b", a["loai"])),
            f"approvals of {persona}",
        )

    def fact_persona(self) -> str:
        """The persona the canon names on its inspection and shipment events."""
        named: set[str] = {
            p
            for e in self.evt
            if e["kind"] in FACT_DOCUMENTS
            for p in re.findall(r"\b(P\d+)\b", e["basis"])
        }
        return _one(sorted(named), "personas handling inspection and shipment")

    def event_basis(self, kind: str, ref: str) -> str:
        return _one(
            (e for e in self.evt if e["kind"] == kind and e["ref"] == ref), f"{kind} on {ref}"
        )["basis"]


def de_scope(canon: Path) -> dict[str, Row]:
    """The canon's ``de_scope`` rows by digital-employee code."""
    return {r["ma_de"]: r for r in _table(canon, "de_scope")}


def _roles(canon: _Canon) -> list[dict[str, str]]:
    scope = de_scope(canon.root)
    out = [{"ma_vai": COORDINATOR, "loai": "dieu_phoi"}]
    for code in DIGITAL_EMPLOYEES:
        duties = core_duties(scope[code])
        out.append(
            {
                "ma_vai": code,
                "loai": "so",
                "soan_bang": "|".join(duties["drafts"]),
                "yeu_cau_duyet": "t" if duties["may_request"] else "",
            }
        )
    people: dict[str, dict[str, set[str]]] = {}
    for loai_pd, persona in canon.deciders.items():
        people.setdefault(persona, {"drafts": set(), "decides": set()})["decides"].add(loai_pd)
    recorder = people.setdefault(canon.fact_persona(), {"drafts": set(), "decides": set()})
    recorder["drafts"] |= {"chung_tu", *FACT_DOCUMENTS.values()}
    for persona in sorted(people, key=lambda p: int(p[1:])):
        out.append(
            {
                "ma_vai": persona,
                "loai": "nguoi",
                "soan_bang": "|".join(sorted(people[persona]["drafts"])),
                "duyet_loai": "|".join(sorted(people[persona]["decides"])),
            }
        )
    invoice_duties = "|".join(sorted({*CORE_TABLES["vinv"], DOCUMENT_TYPES["vinv"]}))
    for vendor in canon.vend:
        out.append({"ma_vai": vendor["ma_ncc"], "loai": "ngoai", "soan_bang": invoice_duties})
    return out


def _policy(canon: _Canon) -> dict[str, Any]:
    rules = []
    for loai_pd, persona in canon.deciders.items():
        label = canon.approval(loai_pd)["loai"]
        rules.append(
            {
                "loai_pd": loai_pd,
                "maker_checker": "maker-checker" in label,
                "tiers": [{"max": None, "nguoi_duyet": persona}],
            }
        )
    return {
        "approval_rules": rules,
        "caps": {DISCOUNT_CAP: str(canon.cap)},
        "tolerances": {},
        "statutory_refs": [],
    }


def _master(canon: _Canon) -> dict[str, str]:
    partners = [
        {"ma_dt": c["ma_kh"], "loai": "khach_hang", "ten": c["ten"], "hang": c["hang"]}
        for c in canon.cust
    ] + [{"ma_dt": v["ma_ncc"], "loai": "nha_cung_cap", "ten": v["ten"]} for v in canon.vend]
    items = [
        {
            "ma_hh": i["ma_sp"],
            "ten": i["ten"],
            "don_vi": UNIT,
            "loai": GOODS,
            "don_gia": i["don_gia"],
            "ton_kho": i["ton_kho"],
            "ck_toi_da": i["ck_toi_da"],
        }
        for i in canon.item
    ]
    staff = [
        {
            "ma_nv": e["ma_nv"],
            "ho_ten": e["ho_ten"],
            "phong_ban": e["phong"],
            "chuc_danh": e["chuc_danh"],
            "luong": e["luong"],
            "trang_thai": e["trang_thai"],
        }
        for e in _table(canon.root, "emp")
    ]
    titles = {k["ma_kb"]: k["tieu_de"] for k in _table(canon.root, "kb")}
    knowledge = []
    for path in sorted((canon.root / "kb").glob("*.md")):
        front = _front_matter(path)
        kb_id = front.get("kb_id", path.stem)
        knowledge.append(
            {
                "ma_kb": kb_id,
                "tieu_de": titles.get(kb_id) or front.get("title", kb_id),
                "linh_vuc": front.get("domain", ""),
            }
        )
    return {
        "doi_tac": _csv(
            partners,
            ["ma_dt", "loai", "ten", "ma_so_thue", "hang", "han_muc_no", "ngan_hang", "stk"],
        ),
        "hang_hoa": _csv(
            items, ["ma_hh", "ten", "don_vi", "loai", "don_gia", "ton_kho", "ck_toi_da"]
        ),
        "nhan_su": _csv(
            staff, ["ma_nv", "ho_ten", "phong_ban", "chuc_danh", "ma_vai", "luong", "trang_thai"]
        ),
        "tri_thuc": _csv(knowledge, ["ma_kb", "tieu_de", "linh_vuc"]),
    }


# --- scenarios and fixture ------------------------------------------------------------------


def _scenarios(canon: _Canon) -> dict[str, Any]:
    raw = json.loads((canon.root / "data" / "scenarios.json").read_text(encoding="utf-8"))
    items = {i["ma_sp"]: i["ten"] for i in canon.item}
    customer = _one((c for c in canon.cust if c["ma_kh"] == canon.so["ma_kh"]), "customers")
    ordered = ", ".join(f"{line['sl']} {items[line['ma_sp']]}" for line in canon.lines)
    scenarios = []
    for s in raw["scenarios"]:
        pct = Decimal(str(s["intake_discount_pct"]))
        scenarios.append(
            {
                "name": s["name"],
                "params": {
                    "intake_discount_pct": s["intake_discount_pct"],
                    "chiet_khau_de_nghi": _number(pct / 100),
                    "grn_received": s["grn_received"],
                },
                "expect": s["expect"],
            }
        )
    payment = canon.approval("de_nghi_chi")
    return {
        "note": raw.get("note", ""),
        "case": {
            "case_id": canon.case["case_id"],
            "title": canon.case["tieu_de"],
            "request": f"{customer['ten']} đặt {ordered}.",
        },
        "readings": {
            "apr_0102": "over_cap when the don_ban document has a FLAGGED event, else normal",
            "three_way": "chung_tu.ket_qua of the hoa_don_mua document",
            "pay_units": "sum of dong_ct.so_luong of the de_nghi_chi document",
            "open_units": "dong_ct.so_luong of don_mua minus that of phieu_nhap",
        },
        "stops_at": {
            "step": WAIT_STEP,
            "for": WAITS_FOR,
            "loai_pd": "de_nghi_chi",
            "ma_pd": payment["ma_apr"],
            "nguoi_duyet": canon.deciders["de_nghi_chi"],
        },
        "scenarios": scenarios,
    }


def _document(
    loai_ct: str,
    ma_ct: str,
    *,
    ma_dt: str | None = None,
    ct_goc: str | None = None,
    lines: list[dict[str, Any]] | None = None,
    ghi_chu: str | None = None,
    event_kind: str | None = None,
) -> dict[str, Any]:
    args: dict[str, Any] = {"loai_ct": loai_ct, "ma_ct": ma_ct}
    if ma_dt is not None:
        args["ma_dt"] = ma_dt
    if ct_goc is not None:
        args["ct_goc"] = ct_goc
    args["lines"] = lines or []
    if ghi_chu is not None:
        args["ghi_chu"] = ghi_chu
    if event_kind is not None:
        args["event_kind"] = event_kind
    return {"tool": "create_document", "args": args}


def _request(approval: Row, loai_pd: str) -> list[dict[str, Any]]:
    return [
        {
            "tool": "request_approval",
            "args": {
                "ma_pd": approval["ma_apr"],
                "ma_ct": approval["hoso_ref"],
                "loai_pd": loai_pd,
            },
        }
    ]


def _decide(approval: Row) -> dict[str, Any]:
    """A person's step: the canon decision, or still pending (an outcome only)."""
    if approval["trang_thai"] == PENDING:
        return {"outcome": "pending"}
    return {
        "tool": "decide_approval",
        "args": {"ma_pd": approval["ma_apr"], "decision": approval["trang_thai"]},
    }


def _received(text: str, received: str) -> str:
    """``text`` with the canon's received quantity replaced by the scenario's."""
    return re.sub(rf"\b{re.escape(received)}\b", "${grn_received}", text)


def _fixture(canon: _Canon) -> dict[str, Any]:
    so, po, grn, vinv = (
        canon.so["ma_so"],
        canon.po["ma_po"],
        canon.grn["ma_grn"],
        canon.vinv["ma_vinv"],
    )
    customer, vendor = canon.so["ma_kh"], canon.po["ma_ncc"]
    short = canon.short["ma_sp"]
    # The scripted digital employee's judgement mirrors the policy cap written to
    # policy.json (ruling R11b): it applies a discount within the cap, and flags one above.
    over = f"chiet_khau_de_nghi > {canon.cap}"
    within = f"chiet_khau_de_nghi <= {canon.cap}"
    cap_row = _cap_row(canon.root)
    label = cap_row["doi_tuong"] if cap_row is not None else f"Trần chiết khấu {canon.cap}"
    cap_text = label[:1].lower() + label[1:]

    def order_lines(discount: Any) -> list[dict[str, Any]]:
        return [
            {
                "ma_dong": line["ma_soline"],
                "ma_hh": line["ma_sp"],
                "so_luong": int(line["sl"]),
                "chiet_khau": discount,
            }
            for line in canon.lines
        ]

    def bought(quantity: Any) -> list[dict[str, Any]]:
        return [{"ma_hh": short, "so_luong": quantity}]

    executor = {
        "lap_don_ban": [
            {
                **_document(
                    "don_ban", so, ma_dt=customer, lines=order_lines("${chiet_khau_de_nghi}")
                ),
                "if": within,
            },
            {**_document("don_ban", so, ma_dt=customer, lines=order_lines(None)), "if": over},
        ],
        "kiem_tra_ton_kho": [
            {"tool": "flag", "args": {"ref": short, "reason": canon.event_basis("FLAGGED", short)}},
            {"outcome": "flag"},
        ],
        "kiem_tra_chiet_khau": [
            {
                "tool": "flag",
                "args": {
                    "ref": so,
                    "reason": f"Khách đề nghị chiết khấu ${{intake_discount_pct}}% vượt {cap_text}",
                },
                "if": over,
            },
            {"outcome": {"if": over, "then": "flag", "else": "pass"}},
        ],
        "trinh_duyet_bao_gia": _request(canon.approval("bao_gia"), "bao_gia"),
        "lap_don_mua": [
            _document("don_mua", po, ma_dt=vendor, ct_goc=so, lines=bought(int(canon.po["sl_dat"])))
        ],
        "trinh_duyet_don_mua": _request(canon.approval("don_mua"), "don_mua"),
        "nhap_kho": [
            _document(
                "phieu_nhap",
                grn,
                ma_dt=vendor,
                ct_goc=po,
                lines=bought("${grn_received}"),
                event_kind="RECEIVED",
            )
        ],
        "lap_hoa_don_ban": [
            _document("hoa_don_ban", canon.inv["ma_inv"], ma_dt=customer, ct_goc=so)
        ],
        "doi_soat_ba_chieu": [
            {"tool": "reconcile", "args": {"doc": vinv, "ordered": po, "received": grn}}
        ],
        "lap_de_nghi_chi": [
            _document(
                "de_nghi_chi",
                canon.pay["ma_pay"],
                ma_dt=vendor,
                ct_goc=vinv,
                lines=bought("${grn_received}"),
            )
        ],
        "trinh_duyet_chi": _request(canon.approval("de_nghi_chi"), "de_nghi_chi"),
    }
    inspection = f"{canon.insp['ket_qua']}. {canon.ncr['ma_ncr']}: " + _received(
        canon.ncr["loi"], canon.grn["sl_nhan"]
    )
    shipment = f"{canon.ship['trang_thai']} {canon.ship['tre_ngay']} ngày".strip()
    environment = {
        "duyet_bao_gia": _decide(canon.approval("bao_gia")),
        "duyet_don_mua": _decide(canon.approval("don_mua")),
        "kiem_tra_chat_luong": _document(
            "bien_ban_kiem_tra",
            canon.insp["ma_insp"],
            ct_goc=grn,
            ghi_chu=inspection,
            event_kind="INSPECTED",
        ),
        "theo_doi_giao_hang": _document(
            "van_don",
            canon.ship["ma_ship"],
            ma_dt=vendor,
            ct_goc=po,
            ghi_chu=shipment,
            event_kind="SHIPPED",
        ),
        # The supplier invoices what was ordered (the canon reconciles PO 15 / GRN 12 / VINV 15).
        "nhan_hoa_don_mua": _document(
            "hoa_don_mua",
            vinv,
            ma_dt=vendor,
            ct_goc=po,
            lines=bought(int(canon.po["sl_dat"])),
            event_kind="RECORDED",
        ),
        "duyet_chi": _decide(canon.approval("de_nghi_chi")),
    }
    return {"executor": executor, "environment": environment}


# --- entry point ----------------------------------------------------------------------------


def convert(canon: Path = CANON_ROOT, out: Path = DEFAULT_OUT) -> None:
    """Write the governance pack for the canon pack ``canon`` into ``out`` (rerunnable)."""
    source = _Canon(Path(canon))
    out = Path(out)
    meta = {
        "name": PACK_NAME,
        "version": source.meta["canon_version"],
        "nguon": source.meta.get("nguon", []),
        "mo_ta": "Gói quản trị chuyển từ canon pack sang lược đồ lõi (C3).",
    }
    roles = _roles(source)
    _write(out / "pack.json", _json(meta))
    _write(
        out / "roles.csv",
        _csv(roles, ["ma_vai", "loai", "soan_bang", "yeu_cau_duyet", "duyet_loai"]),
    )
    _write(out / "policy.json", _json(_policy(source)))
    for name, text in _master(source).items():
        _write(out / "master" / f"{name}.csv", text)
    (out / "kb").mkdir(parents=True, exist_ok=True)
    for path in sorted((source.root / "kb").glob("*.md")):
        shutil.copyfile(path, out / "kb" / path.name)
    _write(out / "scenarios.json", _json(_scenarios(source)))
    _write(out / "fixture.json", _json(_fixture(source)))


if __name__ == "__main__":
    convert()
