"""AgentDojo's prompt-injection detector as published.

The defence is ``agentdojo.agent_pipeline.pi_detector.TransformersBasedPIDetector``,
built with the arguments of AgentDojo's own ``transformers_pi_detector`` pipeline. This
module only calls its ``detect`` and ``transform``: it never blocks a call, it replaces a
tool result (or a delivered message) the detector flags with ``transform``'s text. The
detector is stateless, so one instance serves the process.

Device: the detector runs on the CPU. The original class picks cuda whenever
``torch.cuda.is_available()``; the GPU is shared with Ollama's digital-employee model, and a
detector on it risks an out-of-memory error mid-run or evicting the DE model, which would
distort the other arms' timing. So ``torch.cuda.is_available`` is patched to False only while
the class is constructed (its own device line then picks cpu). The arm's guard latency is
therefore CPU latency.
"""

from __future__ import annotations

import contextlib
import io
import json
import logging
import os
import time
from collections.abc import Mapping
from typing import Any
from unittest import mock

from tonomyx.executors.model import FilterResult

__all__ = ["AgentDojoPIFilter"]

MODEL_NAME = "protectai/deberta-v3-base-prompt-injection-v2"
_detector: Any = None


def _load() -> Any:
    global _detector
    if _detector is None:
        sink = io.StringIO()
        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            prior = logging.root.manager.disable
            logging.disable(logging.WARNING)
            try:
                import torch
                from agentdojo.agent_pipeline.pi_detector import TransformersBasedPIDetector

                # Execution setting, not a method parameter (scores are unchanged): torch's
                # default of one thread per core oversubscribes the CPU next to Ollama
                # (measured 4.0 s/call at 24 threads, 0.34 s/call at 8).
                torch.set_num_threads(min(8, os.cpu_count() or 1))

                with mock.patch("torch.cuda.is_available", return_value=False):
                    _detector = TransformersBasedPIDetector(
                        model_name=MODEL_NAME, safe_label="SAFE", threshold=0.5, mode="message")
            finally:
                logging.disable(prior)
    return _detector


class AgentDojoPIFilter:
    name = "pi"  # the row counter is pi_detections

    def __init__(self) -> None:
        self.detector = _load()

    def _check(self, original: Any, text: str) -> FilterResult:
        started = time.perf_counter()
        sink = io.StringIO()
        with contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
            detected, _score = self.detector.detect(text)
            replaced = ""
            if detected:
                blocks = self.detector.transform([{"type": "text", "content": text}])
                replaced = "".join(b["content"] for b in blocks if b["type"] == "text")
        return FilterResult(content=replaced if detected else original,
                            detected=bool(detected), latency_s=time.perf_counter() - started)

    def filter_message(self, task: str, message: str) -> FilterResult:
        return self._check(message, message)

    def filter_result(
        self, task: str, tool: str, args: Mapping[str, Any], result: Any
    ) -> FilterResult:
        # dumped as _tool_message dumps it, so the detector reads what the model would
        return self._check(result, json.dumps(result, ensure_ascii=False, default=str))
