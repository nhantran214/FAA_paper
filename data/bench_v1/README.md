# FAA Bench v1: case format

A case is a folder of plain files: initial data, roles, policy and a process written as data, and the correct
answer. Nothing in a case folder is code.

This repository holds the 96 cases of the four e-commerce industries (`ban_le`, `phan_phoi`, `van_tai`,
`cntt_phan_mem`): 85 with status `draft_v1` (the runnable paper cases), 10 `dropped` and 1 `planned`. This file
describes the format. The source of truth is in the files named in each section; when they disagree with this text, they
win.

**Isolation.** The answer side of a case (`process.json`, `expected/`, `attacks.json`, `story.md` and the `title` in
`case.meta.json`) is not opened by any person, agent or tool before step 6 of `data/evaluation/RUNBOOK.md`. The
case-input drafter and the expert sheet (RUNBOOK step 3) are the only listed exceptions.

```
data/bench_v1/
  core_schema.json      shared tables, vocabularies, event kinds, money columns   (section 2)
  step_types.json       the closed vocabulary of process steps                    (section 3)
  reference/statutory_vn.json   the only place statutory numbers (VAT, social insurance ...) may come from
  axes.json             the coverage axes: industries, departments and their processes, situation groups and tags,
                        and the implausible industry x process pairs (read by G-blind drafting)
  coverage.json         the coverage matrix: one row per benchmark case (case_id, industry, department, process,
                        situation_group, situation_tag, plausible, note)
  CASE-V1-NNNN/ ...     the benchmark cases
```

## 1. What a case folder contains

| Path | What |
|---|---|
| `case.meta.json` | `case_id`, `title`, `industry`, `department`, `process`, `situation_group` (`normal`, `exception`, `governance`, `attack`, `benign_hard`), `situation_tags`, `status` (`planned`, `generated`, `draft_v1`, `in_review`, `approved`, `rejected`, `dropped`, `fixture`), `extensions`, `generator`; a `dropped` case also has `drop_reason` |
| `story.md` | the case told in plain Vietnamese |
| `schema.json` | `core_tables` used, plus `extensions`: case-specific tables as column lists (`name`, `type`, `pk`, `fk`, `nullable`, and `measure` on numeric columns, section 2). Every extension table has a reason in `case.meta.json` `extensions` (`[{"table", "reason"}]` or `{table: reason}`) |
| `data/<table>.csv` | initial state: master, control and opening operational data. Header = the exact column order of the table definition; a blank cell means "not set". `su_kien` is empty or absent. Opening operational rows (history) belong to an earlier, closed case `<case_id>-LS`, which has the only `data/ho_so.csv` row (see below) |
| `roles.csv` | actors, see below |
| `policy.json` | `approval_rules`, `caps`, `tolerances`, `statutory_refs`, and any other key the case needs, see below |
| `process.json` | `start`, `facts`, `steps` (section 3) |
| `kb/*.md` | knowledge articles the case needs (UTF-8, NFC like every text) |
| `attacks.json` | attack cases only: channel, payload, target step, goal, and `forbidden` outcomes. Each `forbidden` entry `{id, table, where, desc?}` becomes an invariant "no such row" |
| `expected/` | the answer: `final_state/*.csv`, `events.csv`, `outcome.json`, `invariants.json`. It is the full final state of every table, the ordered audit trail, where the run stopped (approvals and their decisions, flags, blocked actions, variables) and checkable facts derived from the result, plus the `forbidden` entries of `attacks.json`. Scoring reads it. Nothing edits it by hand |

**History.** A case's own `ho_so` row is created when its process runs, so opening rows of tables with a `case_id`
column (`chung_tu`, `phe_duyet`) cannot belong to it. They carry the case id `<case_id>-LS`, an earlier, closed case,
and that case's one `data/ho_so.csv` row (`tieu_de` `Hồ sơ trước (lịch sử)`, `trang_thai` `Hoàn tất`). A case without
opening operational rows has no `data/ho_so.csv`.

**`generator`** in `case.meta.json` records how the case was made (model, prompt version and similar). The platform reads
only its `prompt_version`, which `company_pack_from_case` uses as the pack version; that version goes into each row's
governance version.

**`roles.csv`** has the columns `ma_vai`, `loai`, `soan_bang`, `yeu_cau_duyet`, `duyet_loai`. Lists inside a cell are
separated by `|`. `loai` is one of the `actor_kinds` of `step_types.json`.

| `loai` | Who | Permissions in the other columns |
|---|---|---|
| `dieu_phoi` | the coordinator: opens the case, waits or stops | none |
| `so` | a digital employee | `soan_bang`: tables it may draft into (`chung_tu` to create documents); `yeu_cau_duyet` = `t` to request approvals |
| `nguoi` | a human persona | `duyet_loai`: approval types it may decide (for example `don_mua`) |
| `ngoai` | an outside party: carrier, vendor, bank | none; it only records external facts |

**`policy.json`**: `approval_rules` is a list of `{loai_pd, maker_checker?, tiers: [{max, nguoi_duyet}]}`. Tiers are tried
in order; the first whose `max` is `null` or at least the document total wins. `max: null` alone gives "one fixed
approver per approval type". An unknown total cannot enter a tier with a numeric `max`. `maker_checker: true` forbids the
approver from also being the requester or the document author. Every tier approver is a `nguoi` whose
`duyet_loai` lists the rule's `loai_pd`, and there is one rule per `loai_pd`. `caps` (for
example `chiet_khau_toi_da`) and `tolerances` (`gia`: price tolerance for reconciliation) hold canonical numeric text: a
rate as a decimal string (`"0.05"`) or an amount in whole VND (`"10000000"`).
Any other key is allowed (for example a marketing budget `han_muc_mkt`). A process reads a value with
`{"policy": "caps.chiet_khau_toi_da"}`. `statutory_refs` lists the ids of `reference/statutory_vn.json` the case cites.

## 2. Core schema (`core_schema.json`)

All cases share these tables and add extensions only when the process needs them. Columns marked `nullable` in the file
may be blank; every other column must not be blank, in `data/` and in `expected/final_state/`.

| Table | Class | Holds |
|---|---|---|
| `doi_tac` | master | customers, vendors, banks, authorities (`loai`), with tax id, tier, credit limit, bank account |
| `hang_hoa` | master | items and services: unit, `don_gia`, stock, maximum discount `ck_toi_da` (`don_gia` and `ck_toi_da` are base values) |
| `nhan_su` | master | employees and personas, with the role `ma_vai` they play |
| `ngan_sach` | master | budget per department and period: `han_muc`, `da_dung` |
| `tri_thuc` | master | index of knowledge articles (`kb/*.md`) |
| `ho_so` | operational | the case: title and status |
| `chung_tu` | operational | one row per business document: type `loai_ct`, partner, source document `ct_goc`, author, status, reconciliation result, VAT and total |
| `dong_ct` | operational | document lines: item, `so_luong`, `don_gia`, discount, VAT rate, line amount |
| `phe_duyet` | operational | approvals: document, type, requester, approver, value, status |
| `thanh_toan` | operational | payments made |
| `su_kien` | audit, append-only | the event log: `id`, `buoc` (step), `kind`, `ref`, `actor`, `mo_ta` |

Closed vocabularies (`vocab`) cover partner type (`doi_tac.loai`), item type (`hang_hoa.loai`), employee status
(`nhan_su.trang_thai`), case status (`ho_so.trang_thai`), document type and status, reconciliation result (`Khớp`,
`Cần kiểm`), currency (`VND`), approval status and payment status. Event kinds (`event_kinds`) are `DRAFTED`,
`REQUESTED`, `APPROVED`, `REJECTED`, `FLAGGED`, `RECEIVED`, `INSPECTED`, `SHIPPED`, `RECONCILED`, `PAID`, `SENT`,
`STATUS_CHANGED`, `RECORDED`. All text is Unicode NFC.

A numeric column (`int`, `bigint`, `numeric`) of an extension table says what it holds with `measure` in `schema.json`:
`money` (whole VND, never negative), `rate` (between 0 and 1) or `quantity` (a count or an amount of goods, never money).
Money and rate cells are base values (section 6); a quantity is a fact. A numeric extension column must carry one of the
three.

## 3. Process steps (`step_types.json`)

`process.json` is `{"start": id, "facts": {name: value}, "steps": [...]}`. A step is
`{"id", "type", "actor", "params", "next"}`, or `branches` instead of `next`:
`[{"if": expr, "goto": id}, ..., {"else": id}]`, the first `if` that is exactly true wins. The run ends at the first
`wait` or `stop`. A step type outside this table, a missing required param or an unknown param is an error, and the
actor's `loai` must be one the type allows. In the Emits column, `event_kind` means "the kind named by the step's
`event_kind` param", which must be one of `event_kinds` (`step_types.json` writes it as the literal token
`"event_kind"`). Every step is checked this way, also the ones on a branch a run never takes.

| Type | Actor `loai` | Required params | Optional params | Emits |
|---|---|---|---|---|
| `open_case` | dieu_phoi | `title` | | |
| `create_document` | so, nguoi | `doc` | `event_kind` (default `DRAFTED`, `null` = no event) | DRAFTED or `event_kind` |
| `record_external_fact` | nguoi, ngoai | `doc`, `event_kind` | | `event_kind` |
| `check` | so, dieu_phoi | `expr` | `ref`, `flag_reason`, `store` | FLAGGED |
| `flag_exception` | so, nguoi, dieu_phoi | `ref`, `reason` | | FLAGGED |
| `compute_amount` | so, dieu_phoi | `var`, `expr` | | |
| `update_status` | so, nguoi | `table`, `key`, `trang_thai` | | STATUS_CHANGED |
| `request_approval` | so, nguoi | `id`, `doc`, `loai_pd` | | REQUESTED |
| `decide_approval` | nguoi | `approval`, `decision` | `ly_do` | APPROVED, REJECTED |
| `reconcile` | so | `doc`, `ordered`, `received` | | RECONCILED |
| `pay` | so | `id`, `request`, `approval` | `invoice`, `stk_nhan` | PAID, FLAGGED |
| `notify` | so | `ref`, `to`, `approval` | | SENT, FLAGGED |
| `wait` | dieu_phoi | `for` | `approval` | |
| `stop` | dieu_phoi | `reason` | | |

Rules of the process semantics (the answer in `expected/` was produced under them):

- **Documents.** `doc` is `{id, loai_ct, lines, ma_dt?, ct_goc?, trang_thai?, ghi_chu?}`; a line is
  `{ma_dong, so_luong, ma_hh?, mo_ta?, don_gia?, chiet_khau?, thue_suat?}`. A `so` actor needs `chung_tu` in `soan_bang`.
  `ket_qua` cannot be given: only `reconcile` sets it. `trang_thai` cannot be `Chờ duyệt`, `Đã duyệt` or `Từ chối`: a document
  gets those only from `request_approval` and `decide_approval` (gate rule, checked on every step, taken or not).
  A line whose amount comes out negative is an error.
  Text written into a table is stripped and in NFC, exactly as it reads back from the CSV.
- **Approvals.** The requester needs `yeu_cau_duyet` = `t`. The approver is routed by `policy.json` and must be a `nguoi` that lists the
  type in `duyet_loai`. Only that approver can decide, and only while the approval is pending. `decision` is `Đã duyệt` or `Từ chối`.
  **Gates are scoped to the run.** Opening `phe_duyet` and `thanh_toan` rows and opening `ket_qua` values are history: they let a case carry a past
  (a duplicate invoice, a partial payment, an overdue debt) but never satisfy a gate. `decide_approval` on an approval that this run did
  not open with `request_approval` is an error; `pay` and `notify` with such an approval are blocked (see below).
- **`check` with `flag_reason`** must also give `ref` (it becomes the `ref` of the FLAGGED event). The flag is raised when the expression is false.
  **`flag_exception`** needs a non-blank `ref` too.
- **`update_status`** changes `trang_thai` of one row, but never of `phe_duyet`, `thanh_toan` or `su_kien`, and never sets a document to
  `Chờ duyệt`, `Đã duyệt` or `Từ chối`: approvals and payments change only through their own steps (gate rule).
- **`reconcile`** sets `ket_qua` of the invoice to `Khớp` or `Cần kiểm`: ordered, received (a document id or a list) and invoiced
  quantities must agree per item, and prices within `tolerances.gia`. Documents with no item lines at all are an error, not a match.
- **`pay`** and **`notify`** are guarded. `pay` needs an approved approval for the request, opened by this run, and, when given, an
  invoice that a `reconcile` of this run marked `Khớp` (an opening `ket_qua` does not count) and a `stk_nhan` equal to the account on
  file; `notify` needs an approved approval opened by this run, for `ref` itself when `ref` is a document. A refused
  action does not stop the run: it is recorded in `outcome.blocked` and as a FLAGGED event, and nothing else changes. A request is paid
  once (a second `pay` for it is an error), and a known amount must be positive (an unknown, blank amount stays allowed).
- **`wait` and `stop`** end the run. `outcome.stop` always has the five keys `type` (`wait` or `end`), `step`, `for`, `approval`, `reason`.

### Expressions

An expression is JSON and is used in `check`, `compute_amount`, `branches`, line numbers, and in the values of `key` and `where`.

| Form | Value |
|---|---|
| number, string, bool, `null`, list | itself (`"15"` stays a string) |
| `{"var": name}` | a process variable (set by `compute_amount`, `check` with `store`, `reconcile`) |
| `{"fact": name}` | a fact from `process.json` `facts` |
| `{"field": {"table", "key": {col: val}, "col"}}` | one cell; exactly one row must match |
| `{"sum": {"table", "where": {col: val}, "col"}}` | sum of a numeric column; unknown if any cell is blank; 0 for no rows |
| `{"count": {"table", "where"?}}` | number of matching rows |
| `{"policy": "a.b[0].c"}` | a value of `policy.json` by dotted path; numbers (also numeric text) as `Decimal` |
| `{"statutory": id}` | the `Decimal` value of an entry of `reference/statutory_vn.json`, e.g. `{"statutory": "VAT_10"}` |
| `{"op": name, "args": [...]}` | `add` `sub` `mul` `div` `min` `max` `round_vnd` `eq` `ne` `gt` `ge` `lt` `le` `and` `or` `not` |

Numbers are `Decimal`. Unknown stays unknown: arithmetic or comparison with a blank gives unknown, and `and`/`or`/`not` use
three-valued logic. A `check` or a branch on an unknown value is an error, not a silent false. A result too large for
28 significant digits is an error too.

## 4. Numbers and files

- CSV is UTF-8 without BOM, `\n` line ends. Numbers are canonical: `15` not `15.0`, `0.1` not `0.10`.
- Money is a whole number of VND with no separators (`617500`, never `617.500`), never negative. Rates and fractions are
  decimal strings between 0 and 1 (`0.05`). A cell of a numeric column, a literal number on a
  process line, or numeric text in `policy.json` that breaks any of this makes the case invalid.
- The process has no clock and no randomness: event ids are a running integer, so a run is reproducible byte for byte.

## 5. The answer

`expected/` is the correct run of the case's process on its data, computed, never written by hand. The harness scores a
digital employee's run against it: final state, outcome and invariants. It is read at RUNBOOK step 6 and not before.

## 6. Money

- **Base values** are typed in the case: `hang_hoa.don_gia` and `hang_hoa.ck_toi_da`, `doi_tac.han_muc_no`,
  `nhan_su.luong`, `ngan_sach.han_muc` and `da_dung`, `dong_ct.don_gia`, the cells of an extension column whose
  `measure` is `money` or `rate`; in `policy.json` every number except `statutory_refs`; in `process.json` every number
  in `facts`, in a `check` or `compute_amount` expression or a branch condition, and a line's `don_gia` or `chiet_khau`.
  Not base values: the operands `0` and `1` inside an `{"op"}` (as in `1 - rate` or `> 0`), quantities (`so_luong`, and
  extension columns measured as `quantity`), row selectors in `key`/`where`, and values read with `{"policy"}` or
  `{"statutory"}`.
- **Derived values are never typed.** `dong_ct.thanh_tien`, `chung_tu.thue_vat` and `tong_tien` are computed;
  `phe_duyet.gia_tri` is the document total it approves and `thanh_toan.so_tien` is the request it pays.
  `thanh_tien = round(so_luong x don_gia x (1 - chiet_khau))`, `thue_vat` is the sum of the rounded line VAT,
  `tong_tien = sum(thanh_tien) + thue_vat`. Rounding to VND is `Decimal` ROUND_HALF_UP, in a pinned decimal context (28 digits).
- **Unknown stays unknown.** A blank `don_gia` gives a blank line amount and blank document totals; blank is never read as
  zero.
- **Statutory numbers** (VAT rates, cash-payment limit, social insurance) come only from `reference/statutory_vn.json`: listed
  by id in `policy.json` `statutory_refs` and read with `{"statutory": id}`. A case never restates them: a line's
  `thue_suat` in `process.json` is `0` or exactly `{"statutory": ...}`. A non-zero `thue_suat` in an opening
  `data/dong_ct.csv` row equals the value of a `VAT_*` entry listed in `statutory_refs` (compared as numbers). Company
  policy (thresholds, credit limits, budgets, tolerances) lives in `policy.json`.
