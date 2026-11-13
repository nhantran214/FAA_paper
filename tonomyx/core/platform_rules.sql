-- Platform rules at the database tier (spec 5.4). Generic: no trigger names a process.
--
-- Runs after the DDL, inside schema core. The rules read the session values that
-- tonomyx.core.db.acting_as sets with SET LOCAL:
--   tonomyx.actor               the acting role code
--   tonomyx.actor_kind          dieu_phoi | so | nguoi | ngoai  (so = digital employee)
--   tonomyx.governance_version  the governance version that allowed the action
--
-- An action always runs under acting_as. A write with no actor kind set is the
-- platform loading given data (master rows, a case's starting state, released
-- money values), not an action: rules 1-5 and the approver gate bind actors only
-- and stand aside for it. The engine relies on this to load a case (ruling R2a).
-- Rule 6 always holds: the event log is append-only, and an event row needs a
-- session actor and governance version.
--
-- Trust boundary (ruling R2h). This tier trusts the tonomyx.* session settings.
-- Only the platform's tool layer sets them, through acting_as; an actor (digital
-- employee, person, outside party) never gets a raw connection, so it cannot set
-- them itself, nor disable a trigger. The connection runs as the schema owner,
-- which can do both; a separate non-owner database role for acting connections
-- is later hardening (sub-project C).
--
-- Left to the tool tier: the business gate routes every new approval (Task 5/6),
-- so an actor inserting a pending approval routed to itself is the tool tier's to
-- refuse. Here an approval is never inserted already decided, never deleted, and
-- decided only by its routed approver, so such a row can only add to a chain.
--
-- Not enforced here (ruling R2d): the derived amounts (dong_ct.thanh_tien,
-- chung_tu.thue_vat and tong_tien, phe_duyet.gia_tri, thanh_toan.so_tien). The
-- tool tier computes them itself and ignores any value a caller passes (P4).
--
-- Every refusal raises SQLSTATE 42501 (insufficient_privilege) with a message
-- that starts "platform rule N:" (or "platform gate:" for the routed-approver gate,
-- spec 5.3). Within one table and event, PostgreSQL fires
-- BEFORE triggers in name order, so the prN_ prefixes make the lower rule speak
-- first when one write breaks two rules.

CREATE FUNCTION core.session_kind() RETURNS text
LANGUAGE sql STABLE AS $$ SELECT nullif(current_setting('tonomyx.actor_kind', true), '') $$;

CREATE FUNCTION core.session_actor() RETURNS text
LANGUAGE sql STABLE AS $$ SELECT nullif(current_setting('tonomyx.actor', true), '') $$;

CREATE FUNCTION core.session_governance_version() RETURNS text
LANGUAGE sql STABLE AS $$ SELECT nullif(current_setting('tonomyx.governance_version', true), '') $$;


-- Rule 1: a digital employee never approves anything, including its own drafts. -------
-- On an approval, a digital employee may never write a row that reads approved:
-- not by deciding it, not by inserting it approved, not by editing it afterwards.

CREATE FUNCTION core.pr1_approval() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF core.session_kind() = 'so' AND NEW.trang_thai = 'Đã duyệt' THEN
    RAISE EXCEPTION 'platform rule 1: a digital employee never approves (%)', NEW.ma_pd
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER pr1_approval BEFORE INSERT OR UPDATE ON core.phe_duyet
  FOR EACH ROW EXECUTE FUNCTION core.pr1_approval();

-- On a document, a digital employee may not move it into approved. It may still
-- touch an approved document's other fields (a reconciliation result, say).
CREATE FUNCTION core.pr1_document() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF core.session_kind() = 'so' AND NEW.trang_thai = 'Đã duyệt'
     AND (TG_OP = 'INSERT' OR OLD.trang_thai IS DISTINCT FROM 'Đã duyệt') THEN
    RAISE EXCEPTION 'platform rule 1: a digital employee never approves (%)', NEW.ma_ct
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER pr1_document BEFORE INSERT OR UPDATE ON core.chung_tu
  FOR EACH ROW EXECUTE FUNCTION core.pr1_document();


-- Rule 2: the maker of a document is never its checker. -------------------------------
-- The maker of an approval is its requester and the maker of its document. Who
-- made a record is fixed once written, or the rule would fall to two statements:
-- rename the maker, then approve.

CREATE FUNCTION core.pr2_approval() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  actor text := core.session_actor();
BEGIN
  IF core.session_kind() IS NULL THEN
    RETURN NEW;
  END IF;
  IF TG_OP = 'UPDATE' AND (NEW.nguoi_yeu_cau IS DISTINCT FROM OLD.nguoi_yeu_cau
                           OR NEW.ma_ct IS DISTINCT FROM OLD.ma_ct) THEN
    RAISE EXCEPTION 'platform rule 2: an approval''s requester and document are fixed (%)',
      NEW.ma_pd USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF NEW.trang_thai = 'Đã duyệt'
     AND (TG_OP = 'INSERT' OR OLD.trang_thai IS DISTINCT FROM 'Đã duyệt')
     AND (actor = NEW.nguoi_yeu_cau
          OR EXISTS (SELECT 1 FROM core.chung_tu c
                     WHERE c.ma_ct = NEW.ma_ct AND c.nguoi_lap = actor)) THEN
    RAISE EXCEPTION 'platform rule 2: the maker is never the checker (% on %)', actor, NEW.ma_pd
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER pr2_approval BEFORE INSERT OR UPDATE ON core.phe_duyet
  FOR EACH ROW EXECUTE FUNCTION core.pr2_approval();

CREATE FUNCTION core.pr2_document() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  actor text := core.session_actor();
BEGIN
  IF core.session_kind() IS NULL THEN
    RETURN NEW;
  END IF;
  IF TG_OP = 'UPDATE' AND NEW.nguoi_lap IS DISTINCT FROM OLD.nguoi_lap THEN
    RAISE EXCEPTION 'platform rule 2: a document''s maker is fixed (%)', NEW.ma_ct
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF NEW.trang_thai = 'Đã duyệt'
     AND (TG_OP = 'INSERT' OR OLD.trang_thai IS DISTINCT FROM 'Đã duyệt')
     AND (actor = NEW.nguoi_lap
          OR EXISTS (SELECT 1 FROM core.phe_duyet p
                     WHERE p.ma_ct = NEW.ma_ct AND p.nguoi_yeu_cau = actor)) THEN
    RAISE EXCEPTION 'platform rule 2: the maker is never the checker (% on %)', actor, NEW.ma_ct
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER pr2_document BEFORE INSERT OR UPDATE ON core.chung_tu
  FOR EACH ROW EXECUTE FUNCTION core.pr2_document();


-- Rule 3: a digital employee never fills in a money amount without a source. ----------
-- Plan ruling P4, widened by ruling R2b. A unit price a digital employee writes
-- is null, or equals one of:
--   - a money_base column value of any master row (core_schema.json money_base
--     on the master tables; this covers the item's own hang_hoa.don_gia);
--   - the same item's price on a line of the source document (the line's
--     document's ct_goc), when that document belongs to the same case (R2i);
--   - a value the platform released to the line's case in core.nguon_tien.
-- A digital employee can forge none of these: rule 5 shuts it out of the master
-- tables and out of nguon_tien. A person, an outside party or the engine may
-- write any amount.

-- The master money bases, one EXISTS per column. EXISTS never yields null, so a
-- null in a column cannot turn a refusal into a pass.
CREATE FUNCTION core.master_money_value(v bigint) RETURNS boolean
LANGUAGE sql STABLE AS $$
  SELECT EXISTS (SELECT don_gia FROM core.hang_hoa WHERE don_gia = v)
      OR EXISTS (SELECT ck_toi_da FROM core.hang_hoa WHERE ck_toi_da = v)
      OR EXISTS (SELECT han_muc_no FROM core.doi_tac WHERE han_muc_no = v)
      OR EXISTS (SELECT luong FROM core.nhan_su WHERE luong = v)
      OR EXISTS (SELECT han_muc FROM core.ngan_sach WHERE han_muc = v)
      OR EXISTS (SELECT da_dung FROM core.ngan_sach WHERE da_dung = v)
$$;

CREATE FUNCTION core.unit_price_is_sourced(
  p_case_id text, p_ct_goc text, p_ma_hh text, p_don_gia bigint
) RETURNS boolean
LANGUAGE sql STABLE AS $$
  SELECT coalesce(
    p_don_gia IS NULL
    OR core.master_money_value(p_don_gia)
    OR EXISTS (SELECT 1 FROM core.nguon_tien n
               WHERE n.case_id = p_case_id AND n.gia_tri = p_don_gia)
    OR (p_ma_hh IS NOT NULL
        AND EXISTS (SELECT 1 FROM core.dong_ct s
                    JOIN core.chung_tu src ON src.ma_ct = s.ma_ct
                    WHERE s.ma_ct = p_ct_goc AND src.case_id = p_case_id
                      AND s.ma_hh = p_ma_hh AND s.don_gia = p_don_gia)),
    false)
$$;

CREATE FUNCTION core.pr3_line() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  doc core.chung_tu%ROWTYPE;
BEGIN
  IF core.session_kind() = 'so' AND NEW.don_gia IS NOT NULL
     AND (TG_OP = 'INSERT'
          OR NEW.don_gia IS DISTINCT FROM OLD.don_gia
          OR NEW.ma_hh IS DISTINCT FROM OLD.ma_hh
          OR NEW.ma_ct IS DISTINCT FROM OLD.ma_ct) THEN
    SELECT * INTO doc FROM core.chung_tu c WHERE c.ma_ct = NEW.ma_ct;
    IF NOT core.unit_price_is_sourced(doc.case_id, doc.ct_goc, NEW.ma_hh, NEW.don_gia) THEN
      RAISE EXCEPTION 'platform rule 3: unit price % on % has no source', NEW.don_gia, NEW.ma_dong
        USING ERRCODE = 'insufficient_privilege';
    END IF;
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER pr3_line BEFORE INSERT OR UPDATE ON core.dong_ct
  FOR EACH ROW EXECUTE FUNCTION core.pr3_line();

-- Repointing a document's source or case must leave every priced line sourced.
CREATE FUNCTION core.pr3_document_source() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF core.session_kind() = 'so'
     AND (NEW.ct_goc IS DISTINCT FROM OLD.ct_goc OR NEW.case_id IS DISTINCT FROM OLD.case_id)
     AND EXISTS (SELECT 1 FROM core.dong_ct d
                 WHERE d.ma_ct = NEW.ma_ct
                   AND NOT core.unit_price_is_sourced(NEW.case_id, NEW.ct_goc,
                                                      d.ma_hh, d.don_gia)) THEN
    RAISE EXCEPTION 'platform rule 3: changing the source of % leaves a unit price unsourced',
      NEW.ma_ct USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER pr3_document_source BEFORE UPDATE ON core.chung_tu
  FOR EACH ROW EXECUTE FUNCTION core.pr3_document_source();


-- Rule 4: an action that leaves the system needs its linked approval approved. --------
-- Like rules 1-3 and 5, these checks bind actors only: a write with no actor kind
-- (the platform loading given data) stands aside (R2a). Among actors they bind
-- every kind, the engine included, except the payee check and the paid-once check
-- (with its document lock), which bind a digital employee.
--
-- Any write of a payment that reads paid (insert, the move to paid, or any later
-- edit of a paid payment) needs the approval chain of the payment's own document
-- approved (ruling R2c): at least one of its approvals approved, and none pending
-- or rejected. A digital employee pays a document once: it first locks the
-- document row, so two concurrent payments of one document cannot both pass.

CREATE FUNCTION core.pr4_payment() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF core.session_kind() IS NULL OR NEW.trang_thai IS DISTINCT FROM 'Đã chi' THEN
    RETURN NEW;
  END IF;
  IF core.session_kind() = 'so' THEN
    PERFORM 1 FROM core.chung_tu c WHERE c.ma_ct = NEW.ma_ct FOR UPDATE;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM core.phe_duyet p
                 WHERE p.ma_ct = NEW.ma_ct AND p.trang_thai = 'Đã duyệt')
     OR EXISTS (SELECT 1 FROM core.phe_duyet p
                WHERE p.ma_ct = NEW.ma_ct AND p.trang_thai IN ('Chờ duyệt', 'Từ chối')) THEN
    RAISE EXCEPTION 'platform rule 4: payment % needs the approval chain of % approved',
      NEW.ma_tt, NEW.ma_ct USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF core.session_kind() = 'so'
     AND EXISTS (SELECT 1 FROM core.thanh_toan t
                 WHERE t.ma_ct = NEW.ma_ct AND t.trang_thai = 'Đã chi'
                   AND (TG_OP = 'INSERT' OR t.ma_tt IS DISTINCT FROM OLD.ma_tt)) THEN
    RAISE EXCEPTION 'platform rule 4: % is already paid (payment % refused)', NEW.ma_ct, NEW.ma_tt
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER pr4_payment BEFORE INSERT OR UPDATE ON core.thanh_toan
  FOR EACH ROW EXECUTE FUNCTION core.pr4_payment();

-- A paid payment is final: the record that money left is never undone, edited or
-- erased by any actor.
CREATE FUNCTION core.pr4_paid_final() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF core.session_kind() IS NOT NULL AND OLD.trang_thai = 'Đã chi'
     AND (TG_OP = 'DELETE'
          OR NEW.ma_tt IS DISTINCT FROM OLD.ma_tt
          OR NEW.ma_ct IS DISTINCT FROM OLD.ma_ct
          OR NEW.so_tien IS DISTINCT FROM OLD.so_tien
          OR NEW.stk_nhan IS DISTINCT FROM OLD.stk_nhan
          OR NEW.trang_thai IS DISTINCT FROM OLD.trang_thai) THEN
    RAISE EXCEPTION 'platform rule 4: a paid payment is final (%)', OLD.ma_tt
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF TG_OP = 'DELETE' THEN
    RETURN OLD;
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER pr4_paid_final BEFORE UPDATE OR DELETE ON core.thanh_toan
  FOR EACH ROW EXECUTE FUNCTION core.pr4_paid_final();

-- What was approved is what leaves (ruling R2g). A digital employee's payment goes
-- to the paid document's partner account (doi_tac.stk) for the document's
-- tong_tien, exactly; the frozen document below keeps both fixed after approval.
CREATE FUNCTION core.pr4_payee() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  doc_total bigint;
  partner_account text;
BEGIN
  IF core.session_kind() = 'so' THEN
    SELECT c.tong_tien, d.stk INTO doc_total, partner_account
      FROM core.chung_tu c LEFT JOIN core.doi_tac d ON d.ma_dt = c.ma_dt
     WHERE c.ma_ct = NEW.ma_ct;
    IF NEW.stk_nhan IS DISTINCT FROM partner_account THEN
      RAISE EXCEPTION 'platform rule 4: payment % must go to the account of %''s partner',
        NEW.ma_tt, NEW.ma_ct USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF NEW.so_tien IS DISTINCT FROM doc_total THEN
      RAISE EXCEPTION 'platform rule 4: payment % must pay the tong_tien of %',
        NEW.ma_tt, NEW.ma_ct USING ERRCODE = 'insufficient_privilege';
    END IF;
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER pr4_payee BEFORE INSERT OR UPDATE ON core.thanh_toan
  FOR EACH ROW EXECUTE FUNCTION core.pr4_payee();

-- An approved document is frozen (rulings R2g, R2k). Once any approval of a
-- document is approved, its partner, source, case, VAT and total, and its lines,
-- no longer change.
CREATE FUNCTION core.document_is_approved(p_ma_ct text) RETURNS boolean
LANGUAGE sql STABLE AS $$
  SELECT EXISTS (SELECT 1 FROM core.phe_duyet p
                 WHERE p.ma_ct = p_ma_ct AND p.trang_thai = 'Đã duyệt')
$$;

CREATE FUNCTION core.pr4_frozen_document() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF core.session_kind() IS NOT NULL AND core.document_is_approved(OLD.ma_ct)
     AND (NEW.ma_dt IS DISTINCT FROM OLD.ma_dt
          OR NEW.ct_goc IS DISTINCT FROM OLD.ct_goc
          OR NEW.case_id IS DISTINCT FROM OLD.case_id
          OR NEW.thue_vat IS DISTINCT FROM OLD.thue_vat
          OR NEW.tong_tien IS DISTINCT FROM OLD.tong_tien) THEN
    RAISE EXCEPTION 'platform rule 4: approved document is frozen (%)', OLD.ma_ct
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER pr4_frozen_document BEFORE UPDATE ON core.chung_tu
  FOR EACH ROW EXECUTE FUNCTION core.pr4_frozen_document();

CREATE FUNCTION core.pr4_frozen_line() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF core.session_kind() IS NOT NULL THEN
    IF TG_OP IN ('UPDATE', 'DELETE') AND core.document_is_approved(OLD.ma_ct) THEN
      RAISE EXCEPTION 'platform rule 4: approved document is frozen (%)', OLD.ma_ct
        USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF TG_OP IN ('INSERT', 'UPDATE') AND core.document_is_approved(NEW.ma_ct) THEN
      RAISE EXCEPTION 'platform rule 4: approved document is frozen (%)', NEW.ma_ct
        USING ERRCODE = 'insufficient_privilege';
    END IF;
  END IF;
  IF TG_OP = 'DELETE' THEN
    RETURN OLD;
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER pr4_frozen_line BEFORE INSERT OR UPDATE OR DELETE ON core.dong_ct
  FOR EACH ROW EXECUTE FUNCTION core.pr4_frozen_line();

-- The chain is kept. No actor deletes an approval (deleting a pending one would
-- open the way to payment), and no actor truncates the records the chain covers.
CREATE FUNCTION core.pr4_keep_records() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF core.session_kind() IS NOT NULL THEN
    RAISE EXCEPTION 'platform rule 4: actors never erase % (%)', TG_TABLE_NAME, TG_OP
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF TG_LEVEL = 'STATEMENT' THEN
    RETURN NULL;
  END IF;
  RETURN OLD;
END $$;

CREATE TRIGGER pr4_keep_records BEFORE DELETE ON core.phe_duyet
  FOR EACH ROW EXECUTE FUNCTION core.pr4_keep_records();
CREATE TRIGGER pr4_keep_records_truncate BEFORE TRUNCATE ON core.phe_duyet
  FOR EACH STATEMENT EXECUTE FUNCTION core.pr4_keep_records();
CREATE TRIGGER pr4_keep_records_truncate BEFORE TRUNCATE ON core.ho_so
  FOR EACH STATEMENT EXECUTE FUNCTION core.pr4_keep_records();
CREATE TRIGGER pr4_keep_records_truncate BEFORE TRUNCATE ON core.chung_tu
  FOR EACH STATEMENT EXECUTE FUNCTION core.pr4_keep_records();
CREATE TRIGGER pr4_keep_records_truncate BEFORE TRUNCATE ON core.dong_ct
  FOR EACH STATEMENT EXECUTE FUNCTION core.pr4_keep_records();
CREATE TRIGGER pr4_keep_records_truncate BEFORE TRUNCATE ON core.thanh_toan
  FOR EACH STATEMENT EXECUTE FUNCTION core.pr4_keep_records();


-- Rule 5: a digital employee's rights never exceed the platform ceiling. --------------
-- At this tier: master data is written only by a person (actor kind nguoi) or by
-- the platform loading it (no actor kind). A digital employee, an outside party
-- and the engine are refused (ruling R2j). A changed supplier bank account is the
-- classic attack.

CREATE FUNCTION core.pr5_master() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF core.session_kind() IS DISTINCT FROM 'nguoi' AND core.session_kind() IS NOT NULL THEN
    RAISE EXCEPTION 'platform rule 5: only a person writes master data (%, actor kind %)',
      TG_TABLE_NAME, core.session_kind() USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF TG_LEVEL = 'STATEMENT' THEN
    RETURN NULL;
  ELSIF TG_OP = 'DELETE' THEN
    RETURN OLD;
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER pr5_master_write BEFORE INSERT OR UPDATE OR DELETE ON core.doi_tac
  FOR EACH ROW EXECUTE FUNCTION core.pr5_master();
CREATE TRIGGER pr5_master_write BEFORE INSERT OR UPDATE OR DELETE ON core.hang_hoa
  FOR EACH ROW EXECUTE FUNCTION core.pr5_master();
CREATE TRIGGER pr5_master_write BEFORE INSERT OR UPDATE OR DELETE ON core.nhan_su
  FOR EACH ROW EXECUTE FUNCTION core.pr5_master();
CREATE TRIGGER pr5_master_write BEFORE INSERT OR UPDATE OR DELETE ON core.ngan_sach
  FOR EACH ROW EXECUTE FUNCTION core.pr5_master();
CREATE TRIGGER pr5_master_write BEFORE INSERT OR UPDATE OR DELETE ON core.tri_thuc
  FOR EACH ROW EXECUTE FUNCTION core.pr5_master();

CREATE TRIGGER pr5_master_truncate BEFORE TRUNCATE ON core.doi_tac
  FOR EACH STATEMENT EXECUTE FUNCTION core.pr5_master();
CREATE TRIGGER pr5_master_truncate BEFORE TRUNCATE ON core.hang_hoa
  FOR EACH STATEMENT EXECUTE FUNCTION core.pr5_master();
CREATE TRIGGER pr5_master_truncate BEFORE TRUNCATE ON core.nhan_su
  FOR EACH STATEMENT EXECUTE FUNCTION core.pr5_master();
CREATE TRIGGER pr5_master_truncate BEFORE TRUNCATE ON core.ngan_sach
  FOR EACH STATEMENT EXECUTE FUNCTION core.pr5_master();
CREATE TRIGGER pr5_master_truncate BEFORE TRUNCATE ON core.tri_thuc
  FOR EACH STATEMENT EXECUTE FUNCTION core.pr5_master();

-- The platform's released money values are a rule 3 source: no actor writes them,
-- the engine included. Only a write with no actor kind (the platform) may.
CREATE FUNCTION core.pr5_platform_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF core.session_kind() IS NOT NULL THEN
    RAISE EXCEPTION 'platform rule 5: only the platform writes % (actor kind %)',
      TG_TABLE_NAME, core.session_kind() USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF TG_LEVEL = 'STATEMENT' THEN
    RETURN NULL;
  ELSIF TG_OP = 'DELETE' THEN
    RETURN OLD;
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER pr5_platform_write BEFORE INSERT OR UPDATE OR DELETE ON core.nguon_tien
  FOR EACH ROW EXECUTE FUNCTION core.pr5_platform_only();
CREATE TRIGGER pr5_platform_truncate BEFORE TRUNCATE ON core.nguon_tien
  FOR EACH STATEMENT EXECUTE FUNCTION core.pr5_platform_only();


-- Rule 6: every action is an event in an append-only log, with its actor and -------
-- governance version. The session supplies both; a caller's claim is overwritten.
-- So are the event's id (drawn from the table's own sequence; the column has no
-- default) and its time (the clock at insert). These hold with or without an
-- actor kind.

CREATE FUNCTION core.pr6_event() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.kind IS NULL OR NOT (NEW.kind = ANY (core.event_kinds())) THEN
    RAISE EXCEPTION 'platform rule 6: unknown event kind %', coalesce(NEW.kind, 'null')
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  NEW.id := nextval('core.su_kien_id_seq');
  NEW.at := clock_timestamp();
  NEW.actor := core.session_actor();
  IF NEW.actor IS NULL THEN
    RAISE EXCEPTION 'platform rule 6: an event needs a session actor'
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  NEW.governance_version := core.session_governance_version();
  IF NEW.governance_version IS NULL THEN
    RAISE EXCEPTION 'platform rule 6: an event needs a governance version'
      USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER pr6_event BEFORE INSERT ON core.su_kien
  FOR EACH ROW EXECUTE FUNCTION core.pr6_event();

CREATE FUNCTION core.pr6_append_only() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'platform rule 6: % is append-only (%)', TG_TABLE_NAME, TG_OP
    USING ERRCODE = 'insufficient_privilege';
END $$;

CREATE TRIGGER pr6_append_only BEFORE UPDATE OR DELETE ON core.su_kien
  FOR EACH ROW EXECUTE FUNCTION core.pr6_append_only();
CREATE TRIGGER pr6_append_only_truncate BEFORE TRUNCATE ON core.su_kien
  FOR EACH STATEMENT EXECUTE FUNCTION core.pr6_append_only();


-- Platform gate: an approval is decided only by its routed approver (ruling R2c). ------
-- Spec 5.3, database tier. A decision is always an update of a pending approval:
-- no actor inserts one already approved or rejected. An update that leaves the
-- row decided, or moves it out of a decided status (R2i), needs the session actor
-- to be the row's nguoi_duyet. Who an approval is routed to is fixed once
-- written, or the gate would fall to two statements: route it to yourself, then
-- decide. Named prg_ so it fires after rules 1 and 2.

CREATE FUNCTION core.prg_routed_approver() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  actor text := core.session_actor();
BEGIN
  IF core.session_kind() IS NULL THEN
    RETURN NEW;
  END IF;
  IF TG_OP = 'UPDATE' AND NEW.nguoi_duyet IS DISTINCT FROM OLD.nguoi_duyet THEN
    RAISE EXCEPTION 'platform gate: approval decided only by its routed approver (% is routed to %, fixed once written)',
      NEW.ma_pd, OLD.nguoi_duyet USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF TG_OP = 'INSERT' AND NEW.trang_thai IN ('Đã duyệt', 'Từ chối') THEN
    RAISE EXCEPTION 'platform gate: approval decided only by its routed approver (% is inserted decided; a decision updates a pending approval)',
      NEW.ma_pd USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF (NEW.trang_thai IN ('Đã duyệt', 'Từ chối')
      OR (TG_OP = 'UPDATE' AND OLD.trang_thai IN ('Đã duyệt', 'Từ chối')))
     AND actor IS DISTINCT FROM NEW.nguoi_duyet THEN
    RAISE EXCEPTION 'platform gate: approval decided only by its routed approver (% is routed to %, not %)',
      NEW.ma_pd, NEW.nguoi_duyet, actor USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN NEW;
END $$;

CREATE TRIGGER prg_routed_approver BEFORE INSERT OR UPDATE ON core.phe_duyet
  FOR EACH ROW EXECUTE FUNCTION core.prg_routed_approver();
