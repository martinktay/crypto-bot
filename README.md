# 🚀 Crypto Signal Alert Bot (Signal-Only)

Production-minded AI-powered Telegram signal bot with manual approval, signal memory, and a premium monitoring dashboard. **This bot is built on a Signal-Only architecture**, focusing exclusively on high-confidence signal generation without direct exchange execution.

## ✨ Key Features
- **Global Futures Scanner**: Simultaneously scans top-volume Perpetual Swap markets for high-probability setups.
- **Hybrid RL+GA Optimization**: Evolution-based parameter tuning combined with Reinforcement Learning (PPO) for intelligent signal filtering.
- **Neural Lessons (Knowledge Base)**: Uses RAG (Retrieval-Augmented Generation) to recall past market behavior and provide AI-driven reasoning for every signal.
- **Manual Approval Workflow**: 1-click signal vetting via interactive Telegram buttons (✅ Approve / ❌ Reject).
- **Premium Dashboard**: Data-dense, glassmorphism-inspired UI for real-time monitoring and strategy management.

## ⚡ Quick Start

```bash
# 1. Clone and configure
cp .env.example .env
# Edit .env — set TELEGRAM_BOT_TOKEN, TELEGRAM_ADMIN_CHAT_ID, OPENAI_API_KEY

# 2. Start infrastructure (PostgreSQL with pgvector + Redis)
docker compose up -d db redis

# 3. Run migrations
alembic upgrade head

# 4. Install and run
pip install -e .[dev]
uvicorn app.main:app --reload
```

## 🛠 Operation Modes

**Approval modes** (APPROVAL_MODE):
- `auto` — Signals are dispatched to Telegram/WebSockets immediately after risk checks.
- `manual_approval` — Signals require human approval via Telegram before dispatch (default).

## 🧠 Neural Journaling
The bot maintains a "Neural Memory" of past trades and market conditions. 
- **Learning**: Every approved/rejected signal's outcome can be ingested as a "Lesson".
- **Retrieval**: When a new signal is generated, the bot retrieves similar past lessons to refine its AI reasoning.
- **Explainability**: Use `/why` in Telegram or the Dashboard to see the underlying AI rationale for any signal.

## 📊 Dashboard & Monitoring
Access the web dashboard at `http://localhost:8000/`.
- **Trade Metrics Grid**: Real-time signal cards with Entry, TP, SL, and Confidence.
- **Optimization Panel**: Trigger and monitor RL+GA evolution runs live.
- **Neural Insights**: Browse the global knowledge base and recent market lessons.

## 🤖 Telegram Commands

| Command | Access | Description |
|---|---|---|
| `/start` | Public | Welcome message |
| `/status` | Admin | Bot status & health |
| `/signals` | Admin | Recent generated signals |
| `/pause` / `/resume` | Admin | Control scanner state |
| `/why` | Admin | Detailed AI explanation of last signal |
| `/backtest` | Admin | Run historical strategy simulation |
| `/optimize` | Admin | Trigger Hybrid RL+GA optimization |

## 🛡 Safety & Risk
- **Approval Logic**: Mandatory human-in-the-loop for all signal broadcasts by default.
- **Risk Engine**: Enforces Spread, Volatility, and Liquidity filters before signaling.
- **Advisory AI**: AI reasoning is intended for decision support and never overrides core risk rules.

## 🧪 Testing
```bash
pytest tests/ -v
```
