---
name: crypto-bot-builder
description: Build and extend a Telegram crypto signal bot with optional paper trading, manual approval flow, exchange integration, and knowledge base support.
---

# Crypto Bot Builder Skill

## Purpose
This skill helps the agent build, improve, and maintain a production-minded MVP for a Telegram crypto signal bot with optional trade placement and a knowledge base.

## Core mission
Build a backend-first crypto trading assistant that:
1. fetches market data
2. generates signals
3. sends alerts to Telegram
4. supports signal-only, paper, and manual approval modes
5. includes a knowledge base for strategy context and historical trade memory
6. keeps safety, risk controls, and testability as first-class concerns

## Product scope
The project must support:
- Telegram signal delivery
- manual approval workflow in Telegram
- paper trading by default
- signal-only mode
- PostgreSQL persistence
- OpenAI-powered reasoning for signal explanation
- pgvector-backed knowledge retrieval
- Docker local development
- clear README and environment validation

## Required stack
- Python 3.11+
- FastAPI
- python-telegram-bot
- CCXT
- PostgreSQL
- SQLAlchemy or SQLModel
- Alembic
- Redis optional
- APScheduler first, Celery optional later
- pgvector
- OpenAI API
- Docker and docker-compose
- pytest
- gymnasium
- stable-baselines3 or equivalent RL framework

## Non-negotiable safety rules
- Never default to execution-ready modes in sensitive environments
- Never bypass risk rules
- Never hardcode secrets
- Never commit credentials
- Paper trading must be working before manual approval is implemented
- Manual approval flow must work before any automated notification path is enabled

## Project goals
The agent must build these modules:
- app/api
- app/core
- app/db
- app/models
- app/schemas
- app/services
- app/utils
- app/market_data
- app/strategies
- app/risk_management
- app/execution
- app/telegram_bot
- app/approval_workflow
- app/knowledge_base
- app/monitoring
- app/optimization (GA + RL)

## Signal contract
All strategies must return a normalized object with:
- symbol
- timeframe
- signal: LONG | SHORT | HOLD
- entry_price
- stop_loss
- take_profit
- confidence
- reason
- timestamp

## Supported modes
Execution mode:
- signal_only
- paper

Approval mode:
- auto
- manual_approval

Default:
- execution mode = paper
- approval mode = manual_approval

## MVP priority
Build in this exact order:
1. settings/config
2. db models and migrations
3. market data adapter
4. EMA + RSI strategy
5. risk checks
6. paper trading flow
7. Telegram alerts
8. Telegram manual approval
9. knowledge base ingestion and retrieval
10. AI explanation layer
11. API endpoints
12. GA-based hyperparameter optimizer
13. RL-based execution agent
14. README

## MVP constraints
Start with:
- BTC/USDT only
- 15m timeframe only
- EMA crossover + RSI only
- Telegram alerts
- manual approval
- paper trading
- strategy docs + historical trade memory in knowledge base

## Environment contract
Use these env vars:
- APP_ENV
- API_HOST
- API_PORT
- DATABASE_URL
- REDIS_URL
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID
- TELEGRAM_ADMIN_USER_ID
- EXCHANGE_NAME
- EXCHANGE_TESTNET
- DEFAULT_MODE
- APPROVAL_MODE
- RISK_PER_TRADE
- MAX_DAILY_LOSS_PERCENT
- MAX_OPEN_POSITIONS
- SIGNAL_COOLDOWN_MINUTES
- MIN_RISK_REWARD_RATIO
- PAPER_STARTING_BALANCE
- OPENAI_API_KEY
- EMBEDDING_MODEL
- REASONING_MODEL
- SYMBOLS
- TIMEFRAMES
- STRATEGY
- EMA_FAST
- EMA_SLOW
- RSI_PERIOD
- RSI_LONG_THRESHOLD
- RSI_SHORT_THRESHOLD
- TAKE_PROFIT_R_MULTIPLE
- STOP_LOSS_BUFFER_PERCENT
- MANUAL_APPROVAL_TIMEOUT_SECONDS
- SCAN_INTERVAL_SECONDS
- LOG_LEVEL

## Required behavior when invoked
When using this skill, the agent must:
1. inspect the repo first
2. propose a file tree if scaffolding is missing
3. implement incrementally
4. keep the app runnable
5. summarize completed work after each milestone
6. prefer complete working code over placeholders
7. add tests for core logic
8. update README with exact commands
9. validate environment configuration on startup
10. fail safely and log clearly

## Code quality standards
- use type hints
- use pydantic settings
- use dependency injection where helpful
- write readable code
- keep modules small and clear
- add docstrings where they help
- use interfaces or adapters for exchange and AI clients
- design for extension but avoid premature complexity

## Telegram requirements
Must support:
- /start
- /help
- /status
- /positions
- /signals
- /balance
- /mode
- /pause
- /resume
- /why
- /insights

Sensitive actions must check TELEGRAM_ADMIN_USER_ID.

Manual approval mode must send approve/reject inline buttons and expire after timeout.

## Knowledge base requirements
The knowledge base must:
- store strategy documents
- store historical trade outcomes
- support embeddings with pgvector
- retrieve relevant documents for current signals
- retrieve similar historical setups
- build context for AI explanations
- remain advisory only
## Optimization Requirements (GA + RL)
The bot must support a hybrid optimization approach:
- **Genetic Algorithm (GA)**: Use the `OptimizerEngine` to evolve strategy parameters (e.g. EMA periods) across historical data sets to maximize Sharpe ratio or total return.
- **Reinforcement Learning (RL)**: Use a `gym`-compatible environment to train agents that learn to time entries/exits or adjust position sizes.
- **Feature Engineering**: Technical Indicators (RSI, ATR, EMA, Volatility) MUST be used as the primary state features for the RL agent.
- **Safety**: Optimization results (GA or RL) remain advisory only and must never override hard risk management rules.

## Final output expectations
At the end of each major task, provide:
- what was built
- what files changed
- how to run it
- what remains
