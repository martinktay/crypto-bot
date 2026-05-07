import asyncio
import logging
import random
from typing import Any, Dict, List, Optional

from app.api.ws_routes import broadcast_signal
from app.optimization.backtester import BacktestService
from app.optimization.rl_service import RLService
from app.schemas.backtest import BacktestRequest
from app.schemas.optimizer import OptimizerRequest, OptimizerResult
from app.strategies.registry import STRATEGIES

logger = logging.getLogger(__name__)


class OptimizerEngine:
    def __init__(
        self,
        backtester: Optional[BacktestService] = None,
        rl_service: Optional[RLService] = None,
    ) -> None:
        self.backtester = backtester or BacktestService()
        self.rl_service = rl_service or RLService()

    async def run(self, request: OptimizerRequest) -> OptimizerResult:
        """Run the GA in a worker thread to keep the event loop responsive.

        Progress events are pushed to WebSocket clients via a thread-safe
        queue so they don't block the worker.
        """
        logger.info(
            "Starting Hybrid RL+GA Optimization for %s on %s",
            request.strategy_name,
            request.symbol,
        )

        loop = asyncio.get_running_loop()

        def _emit_progress(payload: dict) -> None:
            asyncio.run_coroutine_threadsafe(
                broadcast_signal("optimization_progress", payload),
                loop,
            )

        return await asyncio.to_thread(self._run_sync, request, _emit_progress)

    def _run_sync(
        self,
        request: OptimizerRequest,
        emit_progress,
    ) -> OptimizerResult:
        param_space = self._get_param_space(request.strategy_name)
        population = self._initialize_population(param_space, request.population_size)
        best_overall = None
        all_results = []

        for gen in range(request.generations):
            progress = (gen / request.generations) * 100
            emit_progress({
                "progress": progress,
                "gen": gen + 1,
                "total_gens": request.generations,
            })
            logger.info(
                "Starting Generation %d/%d (%.1f%%)",
                gen + 1,
                request.generations,
                progress,
            )

            fitness_results = []
            for i, params in enumerate(population):
                if request.strategy_name == "hybrid_ai":
                    logger.debug("RL Service 'tuning' individual %d", i)

                backtest_req = BacktestRequest(
                    symbol=request.symbol,
                    timeframe=request.timeframe,
                    strategy_name=request.strategy_name,
                    params=params,
                    days=request.days,
                )
                try:
                    result = self.backtester.run_backtest(backtest_req)
                    fitness = (
                        result.sharpe_ratio
                        if result.sharpe_ratio > 0
                        else (result.final_balance - result.initial_balance)
                    )
                    fitness_results.append((fitness, params, result))
                    all_results.append(result)
                except Exception as exc:
                    logger.error(
                        "Simulation failed for params %s: %s",
                        params,
                        exc.__class__.__name__,
                    )
                    fitness_results.append((-999, params, None))

            fitness_results.sort(key=lambda x: x[0], reverse=True)

            current_best = fitness_results[0]
            if not best_overall or current_best[0] > best_overall[0]:
                best_overall = current_best
                logger.info(
                    "New Best Fitness: %.4f with params %s",
                    best_overall[0],
                    best_overall[1],
                )

            if gen < request.generations - 1:
                population = self._evolve(
                    fitness_results, param_space, request.population_size
                )

        top_performers = sorted(
            all_results, key=lambda x: x.sharpe_ratio, reverse=True
        )[:5]

        if best_overall and best_overall[2]:
            best_return_pct = (
                (best_overall[2].final_balance - best_overall[2].initial_balance)
                / best_overall[2].initial_balance
            ) * 100
        else:
            best_return_pct = 0.0

        final_result = OptimizerResult(
            symbol=request.symbol,
            strategy=request.strategy_name,
            best_params=best_overall[1] if best_overall else {},
            best_sharpe=best_overall[2].sharpe_ratio if best_overall and best_overall[2] else 0.0,
            best_return_pct=best_return_pct,
            total_simulations=len(all_results),
            top_performers=top_performers,
        )

        emit_progress({
            "progress": 100,
            "gen": request.generations,
            "total_gens": request.generations,
        })

        return final_result

    def _get_param_space(self, strategy_name: str) -> Dict[str, Any]:
        """Define valid ranges/options for strategy parameters."""
        if strategy_name == "ema_rsi":
            return {
                "ema_fast": range(5, 20),
                "ema_slow": range(20, 50),
                "rsi_period": range(7, 21),
                "rsi_overbought": range(65, 85),
                "rsi_oversold": range(15, 35),
                "rl_filter": [True, False] # Hybrid addition: Use RL to filter GA signals
            }
        elif strategy_name == "breakout_volume":
            return {
                "window": range(10, 30),
                "volume_factor": [1.5, 2.0, 2.5, 3.0],
                "tp_pct": [0.02, 0.03, 0.05],
                "sl_pct": [0.01, 0.02],
                "rl_adaptive_tp": [True, False] # Hybrid addition
            }
        elif strategy_name == "hybrid_ai":
            return {
                "model_name": ["ppo_trading_bot", "dqn_trading_bot", "a2c_trading_bot"],
                "learning_rate": [0.0001, 0.0003, 0.0007],
                "ent_coef": [0.0, 0.01, 0.05]
            }
        return {}


    def _initialize_population(self, param_space: Dict[str, Any], size: int) -> List[Dict[str, Any]]:
        population = []
        for _ in range(size):
            individual = {}
            for param, options in param_space.items():
                if isinstance(options, range) or isinstance(options, list):
                    individual[param] = random.choice(list(options))
                else:
                    individual[param] = options
            population.append(individual)
        return population

    def _evolve(self, fitness_results: List[tuple], param_space: Dict[str, Any], size: int) -> List[Dict[str, Any]]:
        # Elitism: carry forward top 20%
        elite_count = max(1, size // 5)
        new_population = [fr[1] for fr in fitness_results[:elite_count]]
        
        # Fill rest with Crossover + Mutation
        while len(new_population) < size:
            # Selection (Tournament)
            parents = random.sample(fitness_results[:size // 2], 2)
            p1, p2 = parents[0][1], parents[1][1]
            
            # Crossover
            child = {}
            for param in param_space:
                child[param] = random.choice([p1.get(param), p2.get(param)])
            
            # Mutation (10% chance)
            if random.random() < 0.1:
                param_to_mutate = random.choice(list(param_space.keys()))
                options = param_space[param_to_mutate]
                child[param_to_mutate] = random.choice(list(options))
                
            new_population.append(child)
            
        return new_population
