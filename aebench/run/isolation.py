"""Start each episode from a clean Ollama server.

Why. Ollama's ``llama-server`` keeps one slot and a RAM prompt cache, and every request reuses
the longest token prefix it shares with an earlier one. Prefill runs in 512-token batches, so
when the reused prefix has a different length (a few leading template tokens shared with some
earlier request are enough) the batch boundaries move, the floating-point numerics change
slightly and a greedy model such as qwen3:14b can pick a different reply to a byte-identical
request. A result then depends on which episodes ran before it in the same server. Each
episode must depend only on its own inputs, so before an episode every Ollama model it uses is
unloaded (``keep_alive: 0``): that kills the runner, its slot and its prompt cache, and the next
request reloads the model from scratch.

``unload_ollama_models`` posts the unload for each model, polls ``/api/ps`` until none of them
is listed, then pre-loads each one (a bare ``/api/generate`` with only the model, a
``keep_alive`` and ``options.num_ctx``: it processes no token, so it leaves no KV prefix) and
waits for each to be listed (two models may not fit in GPU memory together; the digital
employee's is loaded last, so it is the one left resident). The pre-load asks for the
experiment's context length (``num_ctx``; the chat clients' ``DEFAULT_NUM_CTX`` when the
experiment sets none; guard models use the same one): Ollama sizes a runner when it loads it,
and a runner loaded at the server's default context would be relaunched by the episode's
first request, inside ``wall_s``. The reload is thus done here, outside the episode's
``wall_s`` and latency figures; only on a GPU that cannot hold the guard model beside the
digital employee's is the guard model still swapped in inside the episode. It raises
``ModelUnavailable`` when the server cannot be reached or a step takes longer than
``timeout`` seconds, so an experiment stops (and resumes later) rather than running a
contaminated episode.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence

import httpx

from aebench.arms.presets import HF_PREFIX
from tonomyx.models.chat import DEFAULT_NUM_CTX, KEEP_ALIVE, _model_error
from tonomyx.models.errors import ModelUnavailable

__all__ = ["episode_ollama_models", "make_isolate", "ollama_server_version",
           "unload_ollama_models"]

UNLOAD_TIMEOUT_S = 60.0
POLL_S = 0.25
VERSION_TIMEOUT_S = 10.0


def episode_ollama_models(model: str, guard_model: str | None) -> list[str]:
    """The Ollama models an episode uses: the digital employee's, and the arm's guard model
    unless it is none or a HuggingFace (``hf:``) model."""
    guard = [guard_model] if guard_model and not guard_model.startswith(HF_PREFIX) else []
    return list(dict.fromkeys([model, *guard]))


def _same(a: str, b: str) -> bool:
    def norm(n: str) -> str:
        return n if ":" in n else f"{n}:latest"

    return norm(a) == norm(b)


def unload_ollama_models(
    models: Sequence[str],
    *,
    ollama_url: str,
    num_ctx: int | None = DEFAULT_NUM_CTX,
    timeout: float = UNLOAD_TIMEOUT_S,
    poll_s: float = POLL_S,
    transport: httpx.BaseTransport | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Unload ``models`` from the server at ``ollama_url``, wait until it lists none of them,
    then load them again, one by one, at context length ``num_ctx`` (``None``: the chat
    clients' ``DEFAULT_NUM_CTX``). Raises ``ModelUnavailable``."""
    names = list(dict.fromkeys(models))
    if not names:
        return
    options = {"num_ctx": num_ctx or DEFAULT_NUM_CTX}
    base = ollama_url.rstrip("/")
    try:
        with httpx.Client(transport=transport, timeout=timeout) as client:

            def wait(want_loaded: bool, only: list[str] | None = None) -> list[str]:
                """Poll ``/api/ps`` until the models are all loaded (or all gone); the names
                still not in that state when ``timeout`` runs out."""
                deadline = time.monotonic() + timeout
                while True:
                    reply = client.get(f"{base}/api/ps")
                    reply.raise_for_status()
                    loaded = [
                        str(m.get("name") or m.get("model") or "")
                        for m in reply.json().get("models", [])
                    ]
                    wrong = [
                        n for n in (only or names)
                        if any(_same(n, x) for x in loaded) != want_loaded
                    ]
                    if not wrong or time.monotonic() >= deadline:
                        return wrong
                    sleep(poll_s)

            for name in names:
                client.post(
                    f"{base}/api/generate", json={"model": name, "keep_alive": 0}
                ).raise_for_status()
            left = wait(False)
            if left:
                raise ModelUnavailable(
                    f"{', '.join(left)}: still loaded {timeout:g} s after the unload"
                )
            # One at a time, the first model (the digital employee's) last: two models may
            # not fit in GPU memory together (qwen3:14b with llama-guard3:8b on 16 GB), and
            # then the later load evicts the earlier one, so each is waited for on its own
            # and the digital employee's, which answers first, is the one left loaded.
            for name in reversed(names):
                client.post(
                    f"{base}/api/generate",
                    json={"model": name, "keep_alive": KEEP_ALIVE, "options": options},
                ).raise_for_status()
                left = wait(True, [name])
                if left:
                    raise ModelUnavailable(
                        f"{name}: not loaded {timeout:g} s after the load request"
                    )
        return
    except (httpx.HTTPError, ValueError, AttributeError) as exc:
        error = _model_error(names[0], exc)
    raise ModelUnavailable(str(error))


def make_isolate(ollama_url: str, *, num_ctx: int | None) -> Callable[[list[str]], None]:
    """The real isolation for the server at ``ollama_url``, pre-loading at ``num_ctx`` (the
    experiment's ``sampling.num_ctx``)."""

    def isolate(models: list[str]) -> None:
        unload_ollama_models(models, ollama_url=ollama_url, num_ctx=num_ctx)

    return isolate


def ollama_server_version(
    ollama_url: str, *, transport: httpx.BaseTransport | None = None
) -> str | None:
    """The Ollama server's version (``GET /api/version``), recorded with every row; ``None``
    when it cannot be read (a diagnostic only: it never stops an experiment)."""
    try:
        with httpx.Client(transport=transport, timeout=VERSION_TIMEOUT_S) as client:
            reply = client.get(f"{ollama_url.rstrip('/')}/api/version")
            reply.raise_for_status()
            version = reply.json().get("version")
    except (httpx.HTTPError, ValueError, AttributeError):
        return None
    return str(version) if version else None
