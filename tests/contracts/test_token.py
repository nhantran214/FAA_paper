"""Task tokens are single use and short lived; user tokens carry a persona."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from tonomyx.contracts.clock import FixedClock
from tonomyx.contracts.token import (
    ISSUER,
    TASK_TOKEN_TTL,
    USER_TOKEN_TTL,
    InMemoryJtiStore,
    TokenExpired,
    TokenIssuer,
    TokenReplayed,
)


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(datetime(2026, 9, 1, 2, 0, tzinfo=UTC))


@pytest.fixture
def issuer(clock: FixedClock) -> TokenIssuer:
    return TokenIssuer(clock=clock, jti_store=InMemoryJtiStore())


def _task_token(issuer: TokenIssuer):
    return issuer.issue_task_token(
        de="DE-SM-02",
        task_id="T-0001",
        case_id="CASE-0031",
        tools={"read_records", "write_draft"},
        read={"cust", "item", "policy"},
        draft={"so", "soline"},
        kb_domain="sales",
        autonomy="L2",
        budget_usd=Decimal("0.05"),
    )


def test_task_token_ttl_is_300_seconds(issuer: TokenIssuer, clock: FixedClock) -> None:
    assert TASK_TOKEN_TTL.total_seconds() == 300
    token = _task_token(issuer)
    assert token.exp == clock.now() + TASK_TOKEN_TTL
    assert token.iss == ISSUER
    assert token.sub == "DE-SM-02"


def test_a_task_token_can_be_redeemed_once(issuer: TokenIssuer) -> None:
    token = _task_token(issuer)
    assert issuer.redeem_task_token(token) is token


def test_replaying_a_task_token_is_refused(issuer: TokenIssuer) -> None:
    token = _task_token(issuer)
    issuer.redeem_task_token(token)
    with pytest.raises(TokenReplayed, match=token.jti):
        issuer.redeem_task_token(token)


def test_an_expired_task_token_is_refused(issuer: TokenIssuer, clock: FixedClock) -> None:
    token = _task_token(issuer)
    clock.advance(301)
    with pytest.raises(TokenExpired):
        issuer.redeem_task_token(token)


def test_an_expired_token_is_not_consumed_and_stays_refused(
    issuer: TokenIssuer, clock: FixedClock
) -> None:
    """Expiry must be checked before the jti is spent, so the error stays honest."""
    token = _task_token(issuer)
    clock.advance(301)
    with pytest.raises(TokenExpired):
        issuer.redeem_task_token(token)
    with pytest.raises(TokenExpired):
        issuer.redeem_task_token(token)


def test_each_task_token_gets_its_own_jti(issuer: TokenIssuer) -> None:
    assert _task_token(issuer).jti != _task_token(issuer).jti


def test_user_token_ttl_is_15_minutes(issuer: TokenIssuer, clock: FixedClock) -> None:
    assert USER_TOKEN_TTL.total_seconds() == 900
    token = issuer.issue_user_token(sub="p2@demo.example", persona="P2", kb_domains={"sales"})
    assert token.exp == clock.now() + USER_TOKEN_TTL
    assert token.persona == "P2"
    assert token.groups == frozenset({"P2"})
    assert issuer.check_user_token(token) is token


def test_an_expired_user_token_is_refused(issuer: TokenIssuer, clock: FixedClock) -> None:
    token = issuer.issue_user_token(sub="p2@demo.example", persona="P2", kb_domains={"sales"})
    clock.advance(901)
    with pytest.raises(TokenExpired):
        issuer.check_user_token(token)


def test_user_tokens_only_carry_demo_addresses(issuer: TokenIssuer) -> None:
    with pytest.raises(ValueError, match="@demo.example"):
        issuer.issue_user_token(sub="real.person@gmail.com", persona="P2", kb_domains={"sales"})
