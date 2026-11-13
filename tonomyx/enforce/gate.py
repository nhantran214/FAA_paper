"""Business gate: policy decisions the tool tier must respect (rules 1, 2)."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from tonomyx.governance.pack import ApprovalRule, Policy


class GateRefused(PermissionError):
    pass


class BusinessGate:
    def __init__(self, policy: Policy) -> None:
        self.policy = policy

    def _rule(self, loai_pd: str) -> ApprovalRule:
        rule = self.policy.approval_rules.get(loai_pd)
        if rule is None:
            raise GateRefused(f"unknown approval type {loai_pd!r}")
        return rule

    def approver_for(self, loai_pd: str, amount: Decimal | None) -> str:
        rule = self._rule(loai_pd)
        for tier in rule.tiers:
            if tier.max is None:
                return tier.approver
            if amount is None:
                raise GateRefused(f"{loai_pd!r} has an amount-bound tier but no amount is known")
            if tier.max >= amount:
                return tier.approver
        raise GateRefused(f"no approval tier covers {loai_pd!r} amount {amount}")

    def may_decide(
        self, approval_row: dict[str, Any], document_row: dict[str, Any], actor: str
    ) -> None:
        loai_pd = approval_row["loai_pd"]
        rule = self._rule(loai_pd)
        gia_tri = approval_row.get("gia_tri")
        try:
            amount = None if gia_tri is None else Decimal(str(gia_tri))
        except InvalidOperation:
            raise GateRefused(f"malformed approval amount {gia_tri!r}") from None
        routed = self.approver_for(loai_pd, amount)
        if actor != routed:
            raise GateRefused(
                f"{actor!r} is not the approver for {loai_pd!r}; routed to {routed!r}"
            )
        if rule.maker_checker:
            if actor == approval_row.get("nguoi_yeu_cau"):
                raise GateRefused(f"maker-checker: {actor!r} requested this approval")
            if actor == document_row.get("nguoi_lap"):
                raise GateRefused(f"maker-checker: {actor!r} made the document")

    def cap_breaches(self, values: dict[str, Decimal]) -> list[str]:
        return sorted(k for k, v in values.items()
                      if k in self.policy.caps and v > self.policy.caps[k])

    def tolerance_breach(self, name: str, expected: Decimal, actual: Decimal) -> bool:
        tol = self.policy.tolerances.get(name)
        if tol is None:
            return actual != expected
        return abs(actual - expected) > tol


class OpenGate(BusinessGate):
    """The business gate switched off (``Controls.gate`` False; experiments only).

    It still routes a new approval as the policy says when the policy covers it (the
    highest tier when the amount is unknown or above every tier), so the people who
    decide find their approvals; an approval type the policy does not know is routed
    to nobody (``UNROUTED``). It lets anyone decide (``may_decide`` never refuses) and
    reports no cap or tolerance breach."""

    UNROUTED = ""

    def approver_for(self, loai_pd: str, amount: Decimal | None) -> str:
        rule = self.policy.approval_rules.get(loai_pd)
        if rule is None or not rule.tiers:
            return self.UNROUTED
        try:
            return super().approver_for(loai_pd, amount)
        except GateRefused:
            return rule.tiers[-1].approver

    def may_decide(
        self, approval_row: dict[str, Any], document_row: dict[str, Any], actor: str
    ) -> None:
        return None

    def cap_breaches(self, values: dict[str, Decimal]) -> list[str]:
        return []

    def tolerance_breach(self, name: str, expected: Decimal, actual: Decimal) -> bool:
        return False
