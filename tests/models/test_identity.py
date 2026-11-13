"""Model identity: Ollama digest, hosted stand-in."""

from __future__ import annotations

import httpx
import pytest

from tonomyx.models.identity import ModelIdentity, model_identity
from tonomyx.models.json_model import ModelUnavailable


def test_identity_reads_ollama_digest() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/show":
            return httpx.Response(200, json={"details": {"family": "qwen"}})
        return httpx.Response(200, json={"models": [
            {"name": "other:1b", "digest": "zzz"}, {"name": "qwen3:8b", "digest": "abc123"}]})

    got = model_identity("qwen3:8b", transport=httpx.MockTransport(handler))
    assert got == ModelIdentity("qwen3:8b", "abc123")

    direct = model_identity("m:1", transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"digest": "d1"})))
    assert direct.digest == "d1"


def test_identity_missing_model_is_unavailable() -> None:
    with pytest.raises(ModelUnavailable):
        model_identity("nope:1", transport=httpx.MockTransport(lambda r: httpx.Response(404)))


def test_identity_hosted() -> None:
    assert model_identity("gemini-2.5-flash") == ModelIdentity(
        "gemini-2.5-flash", "hosted:gemini-2.5-flash")


@pytest.mark.parametrize("response", [
    httpx.Response(200, content=b"<html>proxy</html>"),
    httpx.Response(200, json=["x"]),
])
def test_identity_bad_body_is_model_error(response: httpx.Response) -> None:
    from tonomyx.models.json_model import ModelError

    with pytest.raises(ModelError):
        model_identity("m:1", transport=httpx.MockTransport(lambda r: response))
