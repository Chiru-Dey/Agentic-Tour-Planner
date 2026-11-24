# test_agent.py
"""Pytest gate for CI. Run from repo root:
  pytest evaluation/test_agent.py -m "not llm_judge" --eval-mode mock -q   # cheap
  pytest evaluation/test_agent.py --eval-mode mock -q                      # full (judge on)
"""
import os
import pytest
from evaluation.metrics import BUG_FLAGS

MIN_RECALL = float(os.getenv("EVAL_MIN_RECALL", "0.9"))

def test_tool_selection_custom(record):
    assert record["recall_mean"] >= MIN_RECALL, (
        f"tool recall {record['recall_mean']:.2f} < {MIN_RECALL}; errors={record['errors']}")
    assert not record["forbidden_hits"], f"forbidden tools called: {record['forbidden_hits']}"

def test_data_integrity(record):
    bugs = [(f, ev) for f, ev in record["integrity_flags"] if f in BUG_FLAGS]
    assert not bugs, f"data-integrity bugs detected: {bugs}"

@pytest.mark.llm_judge
def test_hallucination_deepeval(record):
    if record["hallucination_mean"] is None:
        pytest.skip("no tool context or judge disabled")
    assert record["hallucination_mean"] <= 0.5, (
        f"hallucination score {record['hallucination_mean']:.2f}; reasons={record['hall_reasons']}")

def test_tool_correctness_deepeval(record):
    lc = record["last_case"]
    if not lc or not lc["required"]:
        pytest.skip("no expected tools for this scenario")
    from deepeval import assert_test
    from deepeval.metrics import ToolCorrectnessMetric
    from deepeval.test_case import LLMTestCase, ToolCall
    case = LLMTestCase(
        input=lc["input"], actual_output=lc["actual_output"],
        tools_called=[ToolCall(name=t["name"], input_parameters=t["args"]) for t in lc["tools_called"]],
        expected_tools=[ToolCall(name=n) for n in lc["required"]])
    assert_test(case, [ToolCorrectnessMetric(threshold=0.9)])