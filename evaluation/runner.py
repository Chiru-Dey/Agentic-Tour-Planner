"""Shared evaluation engine (used by both pytest and the CLI) + report writer.
Run from the repo root:  python -m evaluation.runner --mode mock --runs 1 --limit 5"""
import argparse, datetime, json, pathlib, statistics, sys, time

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DATASET = pathlib.Path(__file__).parent / "dataset" / "scenarios.json"
REPORTS = pathlib.Path(__file__).parent / "reports"

def load_scenarios(limit: int = 0):
    if not DATASET.exists():
        raise SystemExit("Dataset missing. Run: python evaluation/dataset/build_dataset.py")
    s = json.loads(DATASET.read_text(encoding="utf-8"))
    return s[:limit] if limit else s

def build_eval_graph(provider: str = "groq", temperature: float = 0.0):
    from agent.agentic_workflow import GraphBuilder
    gb = GraphBuilder(model_provider=provider)
    gb.llm.temperature = temperature                      # reproducibility
    gb.llm_with_tools = gb.llm.bind_tools(tools=gb.tools) # re-bind with new temp
    return gb.build_graph()                               # compiled ONCE, reused

def make_judge(model_name: str):
    from evaluation.judge import GroqJudge
    return GroqJudge(model=model_name)

def _hallucination(judge, query, run):
    from deepeval.metrics import HallucinationMetric
    from deepeval.test_case import LLMTestCase
    context = [f"[{t['name']}] {t['content']}" for t in run["tool_outputs"]]
    if not context:
        return None, "no tool context — skipped"
    case = LLMTestCase(input=query, actual_output=run["final_output"], context=context)
    metric = HallucinationMetric(threshold=0.5, model=judge, include_reason=True)
    metric.measure(case)
    return metric.score, metric.reason

def evaluate_scenario(graph, scenario, judge=None, runs=1, sleep_s=0.0):
    from evaluation import metrics as M
    per, errors = [], []
    for i in range(runs):
        try:
            t0 = time.time()
            out = graph.invoke({"messages": [scenario["query"]]})
            run = M.extract_run(out["messages"])
            run["latency"] = time.time() - t0
            run.update(M.tool_scores([t["name"] for t in run["tools_called"]],
                                     scenario["required_tools"], scenario["forbidden_tools"]))
            run["integrity_flags"] = M.integrity_flags(run, scenario["must_mention"])
            run["hallucination"], run["hall_reason"] = None, "judge disabled"
            if judge is not None:
                try:
                    run["hallucination"], run["hall_reason"] = _hallucination(judge, scenario["query"], run)
                except Exception as e:
                    errors.append(f"judge: {e}")
            per.append(run)
        except Exception as e:
            errors.append(f"run {i}: {e}")
        if sleep_s:
            time.sleep(sleep_s)
    if not per:
        return {"id": scenario["id"], "category": scenario["category"], "hits_mean": 0.0,
                "required_count": len(scenario["required_tools"]), "recall_mean": 0.0,
                "strict_pass_rate": 0.0, "hallucination_mean": None, "integrity_flags": [],
                "forbidden_hits": [], "latency_mean": 0.0, "errors": errors,
                "hall_reasons": [], "last_case": None}
    hall = [r["hallucination"] for r in per if r["hallucination"] is not None]
    last = per[-1]
    return {"id": scenario["id"], "category": scenario["category"],
        "hits_mean": statistics.mean(r["hits"] for r in per),
        "required_count": len(scenario["required_tools"]),
        "recall_mean": statistics.mean(r["recall"] for r in per),
        "strict_pass_rate": statistics.mean(float(r["strict_pass"]) for r in per),
        "hallucination_mean": statistics.mean(hall) if hall else None,
        "integrity_flags": [f for r in per for f in r["integrity_flags"]],
        "forbidden_hits": sorted({h for r in per for h in r["forbidden_hits"]}),
        "latency_mean": statistics.mean(r["latency"] for r in per),
        "errors": errors, "hall_reasons": [r["hall_reason"] for r in per],
        "last_case": {"input": scenario["query"], "actual_output": last["final_output"],
                      "tools_called": last["tools_called"], "required": scenario["required_tools"]}}

def compare_reports(a: dict, b: dict) -> str:
    keys = ["micro_tool_recall", "strict_pass_rate", "hallucination_mean", "hallucination_flag_rate"]
    rows = ["| Metric | before | after | delta |", "|---|---|---|---|"]
    for k in keys:
        x, y = a["aggregate"].get(k), b["aggregate"].get(k)
        d = round(y - x, 4) if isinstance(x, (int, float)) and isinstance(y, (int, float)) else "n/a"
        rows.append(f"| {k} | {x} | {y} | {d} |")
    rows.append(f"| bug_flag_counts | {a['aggregate']['bug_flag_counts']} | {b['aggregate']['bug_flag_counts']} | — |")
    return "\n".join(rows)

def main():
    from evaluation import metrics as M
    p = argparse.ArgumentParser(description="Agentic Tour Planner evaluation runner")
    p.add_argument("--mode", choices=["mock", "live"], default="mock")
    p.add_argument("--runs", type=int, default=1)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--provider", default="groq")
    p.add_argument("--judge-model", default="llama-3.3-70b-versatile")
    p.add_argument("--temperature", type=float, default=0.0)
    p.add_argument("--sleep", type=float, default=0.0, help="pause between scenarios (rate limits)")
    p.add_argument("--tag", default="baseline")
    p.add_argument("--no-hallucination", action="store_true", help="skip the LLM judge (free run)")
    p.add_argument("--compare", nargs=2, metavar=("BEFORE_JSON", "AFTER_JSON"))
    args = p.parse_args()

    if args.compare:
        a, b = (json.loads(pathlib.Path(f).read_text()) for f in args.compare)
        print(compare_reports(a, b)); return

    scenarios = load_scenarios(args.limit)
    graph = build_eval_graph(args.provider, args.temperature)
    judge = None if args.no_hallucination else make_judge(args.judge_model)

    from contextlib import nullcontext
    from evaluation.mocks import mocked_apis
    ctx = mocked_apis() if args.mode == "mock" else nullcontext()
    records = []
    with ctx:
        for i, s in enumerate(scenarios, 1):
            print(f"[{i}/{len(scenarios)}] {s['id']} ...", flush=True)
            records.append(evaluate_scenario(graph, s, judge=judge, runs=args.runs, sleep_s=args.sleep))

    agg = M.aggregate(records)
    REPORTS.mkdir(exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    payload = {"tag": args.tag, "mode": args.mode, "runs": args.runs,
               "provider": args.provider, "judge_model": None if judge is None else args.judge_model,
               "aggregate": agg, "records": records}
    jpath = REPORTS / f"{args.tag}_{args.mode}_{ts}.json"
    jpath.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    mpath = REPORTS / f"RESULTS_{args.tag}_{args.mode}.md"
    mpath.write_text(M.results_markdown(args.tag, args.mode, args.runs, agg, records), encoding="utf-8")
    print(json.dumps(agg, indent=2))
    print(f"Saved: {jpath}\nSaved: {mpath}")

if __name__ == "__main__":
    main()