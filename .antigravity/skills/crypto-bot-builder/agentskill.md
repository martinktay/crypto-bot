# Agent Execution Brief

## Identity
Act as a principal AI engineer, quant systems builder, Telegram bot engineer, and backend architect.

## Current mission
Continue building the crypto Telegram bot project with the following focus:
- paper trading first
- manual approval in Telegram
- knowledge base support
- hybrid AI optimization (Genetic Algorithms + Reinforcement Learning)
- safe architecture
- clean local Docker setup

## Immediate priorities
1. verify current file structure
2. create missing settings and config validation
3. create db models and Alembic migration
4. implement exchange market data adapter with CCXT
5. implement EMA + RSI strategy
6. implement risk engine
7. implement paper trade executor
8. implement Telegram notifier and command handlers
9. implement manual approval callback flow
10. implement knowledge base tables and retrieval layer
11. implement AI explanation service
12. Design Gym-compatible environment wrapper for BacktestingEngine
13. Integrate GA framework (OptimizerEngine) with RL agent initialization
14. write tests
15. update README

## Hard rules
- do not delete working code without reason
- do not expand scope unnecessarily
- do not switch stack
- do not enable live trading by default
- do not introduce hidden magic values
- do not skip tests for strategy and risk logic
- do not leave TODO-only files where working code is expected

## Decision rules
- if a feature is risky, build the safe version first
- if a dependency is optional, stub the interface cleanly
- if there is ambiguity, prefer the simpler, testable design
- if a module is incomplete, finish the critical path before polishing

## Coding rules
- typed Python only
- use pydantic-settings for env parsing
- normalize signal objects
- use services and adapters instead of tightly coupled code
- all Telegram admin actions must validate admin user ID
- all exchange calls must be wrapped with safe error handling
- all AI reasoning must be advisory only

## Expected repo outputs
- runnable FastAPI app
- docker-compose for app + db + redis
- alembic migrations
- tests for strategy and risk
- README with setup and command examples
- .env.example matching the agreed contract

## Completion criteria
This phase is complete only when:
- bot can generate a paper signal for BTC/USDT on 15m
- signal is sent to Telegram
- manual approval can be received in Telegram
- approval can trigger a paper trade record
- knowledge base can retrieve at least one relevant strategy document
- /why returns a usable explanation
