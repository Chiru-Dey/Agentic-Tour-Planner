# Agentic Tour Planner 🧳

An intelligent AI-powered trip planner built with **LangGraph**, **LangChain**, **FastAPI**, and **Streamlit**. It helps users plan complete trips with real-time weather, expense calculations, currency conversion, and more.

---
## 🚀 Quick Start

### 1. Clone the repository
```bash
git clone https://github.com/Chiru-Dey/Agentic-Tour-Planner.git
cd Agentic-Tour-Planner
```
### 2. Install dependencies (Recommended: using uv)
```bash
# Install uv (if not installed)
pip install uv
# Create virtual environment and install dependencies
uv venv
uv pip install -r requirements.txt
```
### 3. Set up environment variables
Copy .env.example to .env and add your API keys:
```env
GROQ_API_KEY=your_groq_api_key_here
```
# or
```env
OPENAI_API_KEY=your_openai_api_key_here
```
### 4. Run the application
Option A: Streamlit (Recommended for users)
```bash
streamlit run streamlit_app.py
```
Option B: FastAPI Backend
```bash
uvicorn main:app --reload --port 8000
```

# 🤝 Contributing
Feel free to open issues or submit pull requests!
