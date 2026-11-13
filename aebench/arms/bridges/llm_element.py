"""FAA's ``ChatModel`` as the two LLMs CaMeL talks to (design §6.5, controller rulings 1-2).

CaMeL's privileged LLM (P-LLM) is an AgentDojo pipeline element: ``query`` gets the chat so
far and returns it with one more assistant message, whose text CaMeL reads as the program.
``ChatModelElement`` is that element over FAA's ``ChatModel``, so the P-LLM's calls carry
the experiment's digital-employee model and sampling (temperature 0, seed, ``num_ctx``
32768, think off). It converts AgentDojo's messages (content blocks) to FAA's message dicts
and back, and it removes any ``<think>...</think>`` block from the reply.

CaMeL's quarantined LLM (Q-LLM) is a pydantic-ai ``Agent`` with a ``result_type``.
``quarantined_model`` gives it a pydantic-ai ``FunctionModel`` over the same element:
pydantic-ai's request (its system prompt, the query, its retry prompts and its
``final_result`` output tool) goes to ``ChatModel.chat`` as messages and tools, and the
model's tool call comes back as pydantic-ai's ``ToolCallPart``; pydantic-ai validates and
retries as it does for any model. This is how an OpenAI-compatible endpoint would serve
it (structured output as a tool call), with FAA's sampling.

Both count every call in the element's totals (``prompt_tokens``, ``completion_tokens``,
``latency_s``): everything the agent side spent is the digital employee's cost.

A ``ModelUnavailable`` from the P-LLM propagates as it is (CaMeL calls the P-LLM outside any
``try``). From the Q-LLM it is raised as ``ModelGone``, a ``BaseException``, because CaMeL's
interpreter turns any ``Exception`` a function raises into a program error for the P-LLM to
fix; the executor unwraps it.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from typing import Any

from agentdojo import types as ad_types
from agentdojo.agent_pipeline import BasePipelineElement
from agentdojo.functions_runtime import EmptyEnv, Env, FunctionsRuntime
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ModelResponsePart,
    RetryPromptPart,
    SystemPromptPart,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.tools import ToolDefinition
from pydantic_ai.usage import Usage

from tonomyx.models.chat import ChatModel, ChatReply
from tonomyx.models.errors import ModelUnavailable

__all__ = ["ChatModelElement", "ModelGone", "quarantined_model", "strip_think"]

_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


def strip_think(text: str) -> str:
    """``text`` without its ``<think>...</think>`` blocks."""
    return _THINK.sub("", text).strip()


class ModelGone(BaseException):  # noqa: N818 (a signal, not an error to handle)
    """A ``ModelUnavailable`` raised past CaMeL's ``except Exception`` handlers."""

    def __init__(self, error: ModelUnavailable) -> None:
        super().__init__(str(error))
        self.error = error


def _text(content: Any) -> str:
    """The text of AgentDojo content blocks (or of a plain string)."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return str(ad_types.get_text_content_as_str(list(content)))


def _chat_message(message: ad_types.ChatMessage) -> dict[str, Any]:
    """An AgentDojo chat message as an FAA (Ollama-shaped) message dict."""
    return {"role": message["role"], "content": _text(message.get("content"))}


class ChatModelElement(BasePipelineElement):  # type: ignore[misc]  # agentdojo is untyped
    """An AgentDojo LLM element backed by FAA's ``ChatModel``; see the module docstring."""

    def __init__(self, model: ChatModel) -> None:
        self.model = model
        self.name = model.name
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.latency_s = 0.0
        self.queries = 0  # P-LLM calls (each is one CaMeL turn)

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ChatReply:
        """One call of the model, counted in the element's totals."""
        reply = self.model.chat(messages, tools)
        self.prompt_tokens += reply.prompt_tokens
        self.completion_tokens += reply.completion_tokens
        self.latency_s += reply.latency_s
        return reply

    def query(
        self,
        query: str,
        runtime: FunctionsRuntime,
        env: Env = EmptyEnv(),  # noqa: B008 (AgentDojo's signature)
        messages: Sequence[ad_types.ChatMessage] = (),
        extra_args: dict[str, Any] | None = None,
    ) -> tuple[str, FunctionsRuntime, Env, Sequence[ad_types.ChatMessage], dict[str, Any]]:
        self.queries += 1
        reply = self.chat([_chat_message(m) for m in messages], [])
        message = reply.message if isinstance(reply.message, dict) else {}
        text = strip_think(str(message.get("content") or ""))
        output = ad_types.ChatAssistantMessage(
            role="assistant", content=[ad_types.text_content_block_from_string(text)],
            tool_calls=None,
        )
        return query, runtime, env, [*messages, output], extra_args or {}


# --- the Q-LLM: pydantic-ai FunctionModel over the element ---------------------------


def _user_text(part: UserPromptPart) -> str:
    if isinstance(part.content, str):
        return part.content
    return "\n".join(c for c in part.content if isinstance(c, str))


def _request_messages(request: ModelRequest) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for part in request.parts:
        if isinstance(part, SystemPromptPart):
            out.append({"role": "system", "content": part.content})
        elif isinstance(part, UserPromptPart):
            out.append({"role": "user", "content": _user_text(part)})
        elif isinstance(part, ToolReturnPart):
            out.append({"role": "tool", "tool_name": part.tool_name,
                        "content": part.model_response_str()})
        elif isinstance(part, RetryPromptPart):
            if part.tool_name is None:
                out.append({"role": "user", "content": part.model_response()})
            else:
                out.append({"role": "tool", "tool_name": part.tool_name,
                            "content": part.model_response()})
    return out


def _response_message(response: ModelResponse) -> dict[str, Any]:
    text = "".join(p.content for p in response.parts if isinstance(p, TextPart))
    calls = [{"function": {"name": p.tool_name, "arguments": p.args_as_dict()}}
             for p in response.parts if isinstance(p, ToolCallPart)]
    message: dict[str, Any] = {"role": "assistant", "content": text}
    if calls:
        message["tool_calls"] = calls
    return message


def _messages(history: list[ModelMessage]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for message in history:
        if isinstance(message, ModelRequest):
            out.extend(_request_messages(message))
        else:
            out.append(_response_message(message))
    return out


def _tool(tool: ToolDefinition) -> dict[str, Any]:
    return {"type": "function", "function": {
        "name": tool.name, "description": tool.description,
        "parameters": tool.parameters_json_schema}}


def _arguments(raw: Any) -> dict[str, Any] | str:
    if isinstance(raw, dict | str):
        return raw
    return json.dumps(raw)


def _response(reply: ChatReply) -> ModelResponse:
    message = reply.message if isinstance(reply.message, dict) else {}
    parts: list[ModelResponsePart] = []
    text = strip_think(str(message.get("content") or ""))
    if text:
        parts.append(TextPart(text))
    for call in message.get("tool_calls") or []:
        function = call.get("function") if isinstance(call, dict) else None
        if not isinstance(function, dict):
            continue
        part = ToolCallPart(str(function.get("name") or ""), _arguments(function.get("arguments")))
        if isinstance(call.get("id"), str) and call["id"]:
            part.tool_call_id = call["id"]
        parts.append(part)
    if not parts:
        parts.append(TextPart(""))
    usage = Usage(requests=1, request_tokens=reply.prompt_tokens,
                  response_tokens=reply.completion_tokens,
                  total_tokens=reply.prompt_tokens + reply.completion_tokens)
    return ModelResponse(parts=parts, usage=usage)


def quarantined_model(element: ChatModelElement) -> FunctionModel:
    """A pydantic-ai model that answers through ``element`` (CaMeL's Q-LLM)."""

    async def respond(history: list[ModelMessage], info: AgentInfo) -> ModelResponse:
        tools = [_tool(t) for t in [*info.function_tools, *info.output_tools]]
        try:
            reply = element.chat(_messages(history), tools)
        except ModelUnavailable as exc:
            raise ModelGone(exc) from None
        return _response(reply)

    return FunctionModel(respond, model_name=f"faa:{element.name}")
