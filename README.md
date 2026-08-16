# 🚀 Async AI Agent Orchestration Platform

An enterprise-grade, high-performance **Asynchronous AI Agent Orchestration Platform** built with **FastAPI**, **Redis**, **SQLite**, and a **Native C++ Code Execution Sandbox**. 

Designed for executing complex, multi-step hierarchical agent trees, multi-tool workflows, and parallel worker fan-out with real-time WebSocket telemetry and strict USD/token budget controls.

---

## ✨ Key Features

- 🌳 **Hierarchical DAG Execution Engine**: Supports multi-step reasoning, supervisor-to-worker task delegation (fan-out & fan-in), and dynamic step graph generation.
- ⚡ **Native C++ Code Execution Sandbox**: High-performance compiled C++ module (`pybind11`) providing sandboxed execution with CPU timeout limits and memory quota enforcement.
- 🔌 **Multi-Provider LLM Integration**: Native support for **Google Gemini (e.g. `gemini-2.5-flash`)**, **OpenAI**, and **Anthropic**.
- 📊 **Real-Time Observability Dashboard**: Built-in interactive dashboard served via FastAPI & WebSockets, rendering live DAG tree visualizations, token consumption metrics, and log streams.
- 💰 **Budget & Quota Controls**: Enforces per-agent USD spending limits and token consumption thresholds with automatic circuit-breaking on budget depletion.
- 💾 **Asynchronous Persistence & Queueing**: Powered by `aiosqlite` for trace logging & execution history and `redis` for event queueing and pub/sub broad-casting.

---

## 🏗️ Tech Stack

- **Backend Framework**: Python 3.10+, FastAPI, Uvicorn, Pydantic v2
- **Concurrency & Async**: `asyncio`, `aiosqlite`, `aiohttp`
- **Native Extension**: C++17, `pybind11`, CMake
- **Database & Queueing**: SQLite, Redis 5+
- **LLM SDKs**: `google-genai`, `google-generativeai`, `openai`, `anthropic`
- **Frontend / Dashboard**: Vanilla HTML5/CSS3/JavaScript with real-time WebSockets & SVG DAG renderer

---

## 📂 Project Structure

```
agent-orchestrator/
├── src/
│   ├── backend/
│   │   ├── config.py           # Application settings & environment loader
│   │   ├── main.py             # FastAPI entrypoint, REST routes & WebSockets
│   │   ├── db/                 # SQLite trace repository & Redis connection pools
│   │   ├── engine/             # Core orchestrator engine, state machine, budget manager & fan-out
│   │   ├── llm/                # Multi-LLM provider abstraction layers
│   │   ├── queues/             # Event queuing & message dispatchers
│   │   ├── tools/              # Tool definitions (HTTP fetch, C++ sandbox)
│   │   └── websocket/          # Real-time WebSocket connection manager
│   └── native_sandbox/         # Native C++ sandboxed executor (CMake + pybind11)
├── static/                     # Real-time observability dashboard frontend
├── tests/                      # Pytest async test suite
├── .env.example                # Environment variable configuration template
├── requirements.txt            # Python dependencies
└── README.md                   # Project documentation
```

---

## 🚀 Getting Started

### Prerequisites

- **Python**: 3.10 or higher
- **Redis Server**: Local installation or running via Docker (`docker run -p 6379:6379 redis:alpine`)
- **C++ Compiler** *(Optional for compiling native sandbox)*: GCC/Clang or MSVC supporting C++17

---

### 1. Installation

Clone the repository and set up a virtual environment:

```bash
# Clone repository
git clone https://github.com/CSPruthveesh/agent-orchestrator.git
cd agent-orchestrator

# Create & activate virtual environment
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
```

---

### 2. Environment Configuration

Copy `.env.example` to `.env` and supply your LLM API keys:

```bash
cp .env.example .env
```

Edit `.env` with your preferred settings:

```ini
ENVIRONMENT=development
PROJECT_NAME="Async AI Agent Orchestration Platform"

# Storage & Queue
REDIS_HOST=localhost
REDIS_PORT=6379
SQLITE_DB_PATH=orchestrator.db

# Gemini API Key (Default)
GEMINI_API_KEY=your_gemini_api_key_here
DEFAULT_LLM_MODEL=gemini-2.5-flash

# Execution Limits
SANDBOX_MAX_CPU_TIMEOUT_MS=5000
SANDBOX_MAX_MEMORY_MB=256
MAX_AGENT_TREE_DEPTH=3
DEFAULT_AGENT_BUDGET_USD=1.00
```

---

### 3. Running the Server

Start the Uvicorn ASGI server:

```bash
python -m uvicorn src.backend.main:app --host 0.0.0.0 --port 8000 --reload
```

---

### 4. Accessing the Platform

- 📊 **Real-Time Observability Dashboard**: Open [http://localhost:8000](http://localhost:8000) in your browser.
- 📖 **Interactive API Documentation (Swagger)**: Open [http://localhost:8000/docs](http://localhost:8000/docs).
- 🔌 **WebSocket Endpoint**: `ws://localhost:8000/ws/agent/{agent_id}` or `ws://localhost:8000/ws/global`.

---

## 🛠️ Native C++ Sandbox Build (Optional)

To rebuild the native C++ sandbox bindings:

```bash
cd src/native_sandbox
mkdir build && cd build
cmake ..
cmake --build . --config Release
```

The compiled binary module (`native_sandbox_cpp`) will be copied into `src/backend/tools/`.

---

## 🧪 Running Tests

Execute the automated test suite with `pytest`:

```bash
pytest tests/ -v
```

---

## 📜 License

Distributed under the MIT License. See `LICENSE` for details.
