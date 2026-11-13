"""The defence of a guard arm: what one baseline adds to the digital employee.

A baseline plugs in as one or more of:

- ``guard``: a ``CallGuard`` that reviews each tool call before it runs (Llama Guard 3,
  NeMo Guardrails, Progent);
- ``output_filter``: a ``ToolOutputFilter`` that sees each delivered message and each tool
  result before the model does, and may replace it (the AgentDojo detector, Progent);
- ``executor``: an executor that replaces ``ModelExecutor`` altogether (CaMeL). It keeps
  ``records`` of ``StepRecord`` as ``ModelExecutor`` does, so a row's steps and cost read
  it the same way.

``build_defence`` builds an arm's defence from the company pack, the template and the
models only: no case folder, no answer file. Each baseline's branch is its bridge
(``aebench.arms.bridges``), imported in that branch only, so a run of the TonomyX arms needs
no baseline installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aebench.arms.presets import GUARD_NAMES
from tonomyx.executors.model import CallGuard, ToolOutputFilter
from tonomyx.governance.pack import CompanyPack
from tonomyx.governance.template import ProcessTemplate
from tonomyx.models.chat import ChatModel

__all__ = ["Defence", "build_defence"]


@dataclass(frozen=True)
class Defence:
    guard: CallGuard | None = None
    output_filter: ToolOutputFilter | None = None
    executor: Any | None = None  # an Executor with .records; replaces ModelExecutor (CaMeL)


def build_defence(
    name: str,
    *,
    de_model: ChatModel,
    guard_model: ChatModel | None,
    guard_model_name: str | None,
    pack: CompanyPack,
    template: ProcessTemplate,
    ollama_url: str,
    seed: int | None,
    num_ctx: int | None = None,
) -> Defence:
    """The defence of the guard arm ``name``.

    ``de_model`` is the digital employee's model; ``guard_model`` the client of the arm's
    resolved Ollama guard model (``None`` for a HuggingFace model or no model) and
    ``guard_model_name`` its name; ``ollama_url``, ``seed`` and ``num_ctx`` (the
    experiment's context length; ``None``: the chat clients' default) are the episode's,
    for a bridge that talks to Ollama itself."""
    if name not in GUARD_NAMES:
        raise KeyError(f"no guard arm named {name!r}")
    if name == "llama-guard":
        if guard_model_name is None:
            raise ValueError("the llama-guard arm needs a guard model name (llama-guard3:8b)")
        from aebench.arms.bridges.llama_guard import LlamaGuard3Bridge

        return Defence(guard=LlamaGuard3Bridge(pack, template, model=guard_model_name,
                                               ollama_url=ollama_url, seed=seed,
                                               num_ctx=num_ctx))
    if name == "nemo-guardrails":  # runs no model: guard_model is None by design
        from aebench.arms.bridges.nemo import NeMoBridge

        return Defence(guard=NeMoBridge(pack, template))
    if name == "agentdojo-defense":  # the original PI detector; no LLM
        from aebench.arms.bridges.agentdojo import AgentDojoPIFilter

        return Defence(output_filter=AgentDojoPIFilter())
    if name == "progent":  # secagent talks to the policy model itself: guard_model unused
        if guard_model_name is None:
            raise ValueError("the progent arm needs a guard model name (the experiment's"
                             " guard_model, its policy model)")
        from aebench.arms.bridges.progent import ProgentBridge

        bridge = ProgentBridge(pack, template, policy_model=guard_model_name,
                               ollama_url=ollama_url, seed=seed, num_ctx=num_ctx)
        return Defence(guard=bridge, output_filter=bridge)
    if name == "camel-capability":  # CaMeL is the agent: its P-LLM and Q-LLM are the DE model
        from aebench.arms.bridges.camel import CaMeLExecutor

        return Defence(executor=CaMeLExecutor(de_model, pack, template, policy_prompt=True))
    raise NotImplementedError(name)
