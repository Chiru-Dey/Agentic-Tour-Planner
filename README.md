# 🧳 Agentic Tour Planner

An AI travel agent that plans complete trips using a **LangGraph ReAct agent**. Give it a
destination and duration — it autonomously calls weather, place-search, budget, and currency
tools, then returns a full Markdown itinerary with real-time data and a cost breakdown.

**Stack:** LangGraph · LangChain · Groq (DeepSeek/Llama) or OpenAI · FastAPI · Streamlit · uv

## ✨ Features

- 🤖 **Agentic tool use** — the LLM decides which of 10 tools to call and when to stop (ReAct loop)
- 🌦️ Real-time weather (OpenWeatherMap) · 📍 POI search (Google Places, **Tavily web-search fallback**)
- 💰 Deterministic budget math (Python tools, not LLM arithmetic) · 💱 live currency conversion
- 🗺️ Two plans per trip: classic tourist highlights + off-beat locations
- 🧪 **Evaluation harness**: DeepEval + pytest over 55 ground-truth scenarios (see `evaluation/`)

## 🏗️ Architecture

```
Streamlit UI ──POST /query──► FastAPI ──invoke──► LangGraph agent (Groq/OpenAI)
                                                   │  ReAct loop: agent ⇄ tools
                    ┌──────────────┬───────────────┼─────────────────┐
                 Weather        Places          Calculators       Currency
              (OpenWeatherMap) (Google→Tavily)  (pure Python)  (ExchangeRate-API)
```

The graph: `START → agent → (tool calls? → tools → agent) → END`.
State is a LangGraph `MessagesState`; the system prompt lives in `prompt_library/prompt.py`.

## 📁 Project structure

```
agent/            LangGraph workflow (GraphBuilder)
tools/            LangChain @tool wrappers the LLM can call
utils/            Raw API clients & business logic (no LangChain here)
config/           config.yaml — model names per provider
prompt_library/   System prompt
evaluation/       DeepEval + pytest harness, 55-scenario dataset, reports
main.py           FastAPI backend
streamlit_app.py  Streamlit frontend
```

## 🚀 Quick start (uv-native)

Requires Python 3.10+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/Chiru-Dey/Agentic-Tour-Planner.git
cd Agentic-Tour-Planner
uv sync                      # deps + project (editable) + dev tools
cp .env.example .env         # then fill in your keys
```

### API keys

| Variable | Used for | Required |
|---|---|---|
| `GROQ_API_KEY` | LLM (default provider) — console.groq.com | ✅ (or OpenAI) |
| `OPENAI_API_KEY` | Alternative LLM | optional |
| `OPENWEATHERMAP_API_KEY` | Weather tools — openweathermap.org | for weather |
| `GPLACES_API_KEY` | Google Places POI search | for place tools |
| `TAVILY_API_KEY` | Fallback web search — tavily.com | for fallback |
| `EXCHANGE_RATE_API_KEY` | Currency conversion — exchangerate-api.com | for FX |

### Run (two terminals)

```bash
uv run uvicorn main:app --reload --port 8000   # backend  (API docs: http://localhost:8000/docs)
uv run streamlit run streamlit_app.py          # frontend (needs the backend running)
```

```bash
curl -X POST http://localhost:8000/query -H "Content-Type: application/json" \
     -d '{"question": "Plan a 5-day trip to Goa"}'
```

### Switching models

Edit `config/config.yaml`. ⚠️ Use a model currently served by your provider that supports
tool calling (check Groq's model list — older DeepSeek distills have been deprecated).

## 🧪 Evaluation

```bash
uv run python evaluation/dataset/build_dataset.py                       # 55 scenarios
uv run python -m evaluation.runner --mode mock --runs 3 --tag baseline  # measure
uv run pytest evaluation/test_agent.py -m "not llm_judge" --eval-mode mock -q
```

- **Tool-call accuracy**: micro-averaged recall of required tools actually called (order-agnostic),
  plus a strict pass-rate (all required, zero forbidden).
- **Hallucination**: DeepEval `HallucinationMetric` — an LLM judge (different model from the agent)
  checks the final plan for contradictions against captured tool outputs.
- **Data-integrity checks**: deterministic detectors (e.g., Kelvin reported as °C, string-typed cost math).
- Mock mode patches the HTTP layer (faithful to real API contracts) so runs are cheap and
  reproducible; the LLM and judge still run live. Results are committed under `evaluation/reports/`.


## 🤝 Contributing

Issues and PRs welcome. Run the eval suite before submitting changes.