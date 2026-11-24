# conftest.py
import os, pathlib, sys
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")

from evaluation.runner import load_scenarios, build_eval_graph, evaluate_scenario, make_judge

def pytest_addoption(parser):
    parser.addoption("--eval-mode", default="mock", choices=["mock", "live"])
    parser.addoption("--eval-runs", default=1, type=int)
    parser.addoption("--eval-limit", default=0, type=int)
    parser.addoption("--eval-provider", default="groq")
    parser.addoption("--eval-judge-model", default="llama-3.3-70b-versatile")

def pytest_generate_tests(metafunc):
    if "scenario" in metafunc.fixturenames:
        s = load_scenarios(metafunc.config.getoption("--eval-limit"))
        metafunc.parametrize("scenario", s, ids=[x["id"] for x in s])

@pytest.fixture(scope="session")
def graph(request):
    return build_eval_graph(request.config.getoption("--eval-provider"), temperature=0.0)

@pytest.fixture(scope="session", autouse=True)
def api_mocks(request):
    if request.config.getoption("--eval-mode") == "mock":
        from evaluation.mocks import mocked_apis
        with mocked_apis():
            yield
    else:
        yield

@pytest.fixture(scope="session")
def judge(request):
    if "not llm_judge" in (request.config.getoption("markexpr") or ""):
        return None                       # cheap runs: no judge tokens spent
    return make_judge(request.config.getoption("--eval-judge-model"))

@pytest.fixture(scope="session")
def eval_cache():
    return {}

@pytest.fixture
def record(scenario, graph, judge, eval_cache, request):
    if scenario["id"] not in eval_cache:  # invoke agent once per scenario, share across tests
        eval_cache[scenario["id"]] = evaluate_scenario(
            graph, scenario, judge=judge, runs=request.config.getoption("--eval-runs"))
    return eval_cache[scenario["id"]]