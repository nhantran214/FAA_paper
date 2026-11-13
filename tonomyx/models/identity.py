"""Which model produced a result: its name and a digest that pins the weights."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from tonomyx.models.json_model import ModelError, ModelUnavailable

SHOW_TIMEOUT = 30.0


@dataclass(frozen=True)
class ModelIdentity:
    name: str
    digest: str


def _object(response: httpx.Response) -> dict[str, Any]:
    try:
        value = response.json()
    except ValueError:
        raise ModelError("Ollama answered with a body that is not JSON") from None
    if not isinstance(value, dict):
        raise ModelError("Ollama answered with a body that is not a JSON object")
    return value


def model_identity(
    name: str,
    *,
    ollama_url: str = "http://localhost:11434",
    transport: httpx.BaseTransport | None = None,
) -> ModelIdentity:
    """A hosted model has no digest to read, so its name stands in for one."""
    if name.startswith("gemini-"):
        return ModelIdentity(name, f"hosted:{name}")
    try:
        with httpx.Client(transport=transport, timeout=SHOW_TIMEOUT) as client:
            base = ollama_url.rstrip("/")
            response = client.post(f"{base}/api/show", json={"model": name})
            if response.status_code != httpx.codes.OK:
                raise ModelUnavailable(f"{name}: /api/show answered {response.status_code}")
            body = _object(response)
            details = body.get("details")
            details = details if isinstance(details, dict) else {}
            digest = str(body.get("digest") or details.get("digest") or "")
            if not digest:
                # Real Ollama lists the digest in /api/tags, not in /api/show.
                tags = client.get(f"{base}/api/tags")
                tags.raise_for_status()
                wanted = {name, f"{name}:latest"} if ":" not in name else {name}
                listed = _object(tags).get("models")
                for entry in listed if isinstance(listed, list) else []:
                    if isinstance(entry, dict) and wanted & {entry.get("name"), entry.get("model")}:
                        digest = str(entry.get("digest") or "")
                        break
    except httpx.TransportError as exc:
        raise ModelUnavailable(f"cannot reach Ollama: {type(exc).__name__}") from None
    except httpx.HTTPStatusError as exc:
        raise ModelUnavailable(f"Ollama answered {exc.response.status_code}") from None
    if not digest:
        raise ModelUnavailable(f"{name}: Ollama reported no digest")
    return ModelIdentity(name, digest)
