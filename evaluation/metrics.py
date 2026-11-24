"""Deterministic extraction, tool-call scoring, data-integrity checks, aggregation.
No LLM calls here — this half of the suite is free and fully reproducible."""
import re
from collections import Counter

def extract_run(messages):
    tools_called, tool_outputs = [], []
    for m in messages:
        for tc in (getattr(m, "tool_calls", None) or []):
            tools_called.append({"name": tc["name"], "args": tc.get("args", {})})
        if getattr(m, "type", "") == "tool":
            tool_outputs.append({"name": getattr(m, "name", "tool"), "content": str(m.content)})
    final = ""
    for m in reversed(messages):
        if getattr(m, "type", "") == "ai" and m.content and not getattr(m, "tool_calls", None):
            final = str(m.content); break
    if not final and messages:
        final = str(getattr(messages[-1], "content", messages[-1]))
    return {"final_output": final, "tools_called": tools_called,
            "tool_outputs": tool_outputs, "n_tool_calls": len(tools_called)}

def tool_scores(called_names, required, forbidden):
    called = set(called_names); req = set(required)
    hits = len(called & req)
    recall = hits / len(req) if req else 1.0   # no required tools -> vacuous pass
    forbidden_hits = sorted(called & set(forbidden))
    strict_pass = req.issubset(called) and not forbidden_hits
    return {"hits": hits, "required_count": len(req), "recall": recall,
            "forbidden_hits": forbidden_hits, "strict_pass": strict_pass}

def integrity_flags(run, must_mention):
    flags = []
    for t in run["tool_outputs"]:
        name, content = t["name"], t["content"].strip()
        if name == "get_current_weather":
            m = re.search(r"(-?\d+(?:\.\d+)?)\s*°C", content)
            if m and float(m.group(1)) > 120:
                flags.append(("kelvin_as_celsius", content[:80]))
        if name == "estimate_total_hotel_cost":
            if re.fullmatch(r"(\d{2,6})\1{2,}", content) or re.fullmatch(r"\d{10,}", content):
                flags.append(("string_multiplication", content[:80]))
        if content in ("None", ""):
            flags.append(("silent_none_output", name))
        if "Google cannot find" in content:
            flags.append(("tavily_fallback_used", name))   # informational, not a bug
    low = run["final_output"].lower()
    for token in must_mention:
        if token and token not in low:
            flags.append(("missing_destination", token))
    return flags

BUG_FLAGS = {"kelvin_as_celsius", "string_multiplication", "silent_none_output", "missing_destination"}

def aggregate(records):
    scored = [r for r in records if r.get("required_count", 0) > 0]
    hits = sum(r["hits_mean"] for r in scored); req = sum(r["required_count"] for r in scored)
    judged = [r for r in records if r.get("hallucination_mean") is not None]
    bugs = Counter()
    for r in records:
        for f in {f for f, _ in r["integrity_flags"]} & BUG_FLAGS:
            bugs[f] += 1
    return {
        "n_scenarios": len(records),
        "micro_tool_recall": round(hits / req, 4) if req else None,
        "macro_tool_recall": round(sum(r["recall_mean"] for r in records) / len(records), 4) if records else None,
        "strict_pass_rate": round(sum(r["strict_pass_rate"] for r in records) / len(records), 4) if records else None,
        "hallucination_mean": round(sum(r["hallucination_mean"] for r in judged) / len(judged), 4) if judged else None,
        "hallucination_flag_rate": round(sum(r["hallucination_mean"] > 0 for r in judged) / len(judged), 4) if judged else None,
        "n_judged": len(judged),
        "fallback_scenarios": sum(any(f == "tavily_fallback_used" for f, _ in r["integrity_flags"]) for r in records),
        "bug_flag_counts": dict(bugs),
        "errors": sum(bool(r.get("errors")) for r in records),
        "mean_latency_s": round(sum(r["latency_mean"] for r in records) / len(records), 2) if records else None,
    }

def results_markdown(tag, mode, runs, agg, records):
    lines = [f"# Eval results — `{tag}` ({mode} mode, {runs} run(s)/scenario)", "",
        "| Metric | Value |", "|---|---|"]
    for k, v in agg.items():
        lines.append(f"| {k} | {v} |")
    lines += ["", "## Failing / flagged scenarios", "",
        "| id | category | recall | strict | halluc. | flags |", "|---|---|---|---|---|---|"]
    for r in records:
        flags = ",".join(sorted({f for f, _ in r["integrity_flags"]})) or "—"
        if r["recall_mean"] < 1.0 or r["strict_pass_rate"] < 1.0 or (r["hallucination_mean"] or 0) > 0 or flags != "—" or r.get("errors"):
            lines.append(f"| {r['id']} | {r['category']} | {r['recall_mean']:.2f} | {r['strict_pass_rate']:.2f} | "
                         f"{r['hallucination_mean'] if r['hallucination_mean'] is not None else 'n/a'} | {flags} |")
    return "\n".join(lines) + "\n"