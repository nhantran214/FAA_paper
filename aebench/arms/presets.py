"""The arms of the evaluation (plan ruling Q1): which tiers run, and what the model is told.

An arm is the same engine and the same model-backed digital employee with:

- ``controls``: the enforcement tiers switched on (``tonomyx.enforce.controls``);
- ``policy_prompt``: whether the platform rules and the company policy are in the
  digital employee's system prompt;
- ``guard``: the baseline defence (``aebench.arms.defence.build_defence``) of a guard arm,
  or ``None``;
- ``guard_model``: the model the defence's authors use, fixed per arm so an experiment
  file cannot mis-set it: an Ollama model name, ``hf:<repo id>`` for a HuggingFace model
  run in process, ``GUARD_MODEL_REF`` for the experiment's ``guard_model``, or ``None``
  when the defence calls no model of its own.

``full`` is the platform; ``no-database`` drops only the rule triggers, which isolates the
database tier; ``prompt-only`` keeps the rules as text alone; ``bare`` has neither tiers nor
rules; each guard arm is ``prompt-only`` with that defence added.
"""

from __future__ import annotations

from dataclasses import dataclass

from tonomyx.enforce.controls import FULL, NONE, Controls

GUARD_NAMES = (
    "progent", "llama-guard", "nemo-guardrails", "agentdojo-defense", "camel-capability",
)
# A guard arm's ``guard_model`` that stands for the experiment's ``guard_model``.
GUARD_MODEL_REF = "@guard_model"
# The prefix of a guard model that is a HuggingFace repository, not an Ollama model.
HF_PREFIX = "hf:"

# The authors' model of each guard arm: Progent's policy model is the experiment's general
# model; NeMo's action rails call no model; CaMeL's P-LLM and Q-LLM are the DE model.
GUARD_MODELS: dict[str, str | None] = {
    "progent": GUARD_MODEL_REF,
    "llama-guard": "llama-guard3:8b",
    "nemo-guardrails": None,
    "agentdojo-defense": f"{HF_PREFIX}protectai/deberta-v3-base-prompt-injection-v2",
    "camel-capability": None,
}


@dataclass(frozen=True)
class Arm:
    name: str
    controls: Controls
    policy_prompt: bool
    guard: str | None
    guard_model: str | None = None


def _table() -> dict[str, Arm]:
    arms = [
        Arm("full", FULL, True, None),
        Arm("no-database", Controls(tokens=True, gate=True, database=False), True, None),
        Arm("prompt-only", NONE, True, None),
        Arm("bare", NONE, False, None),
    ]
    arms += [Arm(name, NONE, True, name, GUARD_MODELS[name]) for name in GUARD_NAMES]
    return {arm.name: arm for arm in arms}


ARMS: dict[str, Arm] = _table()
