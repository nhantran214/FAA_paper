import json
from decimal import Decimal

from tonomyx.governance.pack import load_company_pack


def make_pack(d):
    (d / "kb").mkdir(parents=True)
    (d / "master").mkdir()
    (d / "pack.json").write_text(json.dumps({"name": "demo", "version": "1.2"}))
    (d / "roles.csv").write_text(
        "ma_vai,loai,soan_bang,yeu_cau_duyet,duyet_loai\n"
        "DP,dieu_phoi,,,\n"
        "DE,so,chung_tu|phieu,t,\n"
        "KT,nguoi,,,de_nghi_chi|don_mua\n")
    (d / "policy.json").write_text(json.dumps({
        "approval_rules": [{"loai_pd": "de_nghi_chi", "maker_checker": True,
                            "tiers": [{"max": 200000000, "nguoi_duyet": "KT"},
                                      {"max": None, "nguoi_duyet": "GD"}]}],
        "caps": {"han_muc": "2475000000"},
        "tolerances": {"gia": "0.02"},
        "statutory_refs": ["VAT_10"]}))
    (d / "kb" / "a1.md").write_text("# Quy dinh\nNoi dung\n")
    (d / "master" / "hang_hoa.csv").write_text("ma,ten\nH1,Gao\nH2,Muoi\n")


def test_load_company_pack_from_directory(tmp_path):
    make_pack(tmp_path)
    p = load_company_pack(tmp_path)
    assert (p.name, p.version) == ("demo", "1.2")
    de = next(r for r in p.roles if r.code == "DE")
    assert de.kind == "so" and de.drafts == frozenset({"chung_tu", "phieu"})
    assert de.may_request is True and de.decides == frozenset()
    kt = next(r for r in p.roles if r.code == "KT")
    assert kt.may_request is False and kt.decides == frozenset({"de_nghi_chi", "don_mua"})
    rule = p.policy.approval_rules["de_nghi_chi"]
    assert rule.maker_checker is True
    assert rule.tiers[0].max == Decimal("200000000") and rule.tiers[0].approver == "KT"
    assert rule.tiers[1].max is None
    assert p.policy.caps["han_muc"] == Decimal("2475000000")
    assert p.policy.tolerances["gia"] == Decimal("0.02")
    assert p.policy.statutory_refs == ("VAT_10",)
    assert p.kb[0].id == "a1" and p.kb[0].title == "Quy dinh"
    assert p.master["hang_hoa"] == [{"ma": "H1", "ten": "Gao"}, {"ma": "H2", "ten": "Muoi"}]
