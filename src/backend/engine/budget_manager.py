import redis.asyncio as aioredis
from typing import Optional, Dict, Any
from src.backend.db.database import get_redis_client


class BudgetExceededException(Exception):
    """
    Raised when an agent's cumulative token spend exceeds its configured dollar ceiling.
    """
    def __init__(self, agent_id: str, current_spend_usd: float, max_budget_usd: float):
        self.agent_id = agent_id
        self.current_spend_usd = current_spend_usd
        self.max_budget_usd = max_budget_usd
        message = (
            f"Agent '{agent_id}' exceeded dollar budget ceiling: "
            f"${current_spend_usd:.4f} >= max budget ${max_budget_usd:.4f}"
        )
        super().__init__(message)


class TokenBudgetManager:
    """
    Async middleware enforcer utilizing atomic Redis counters (`INCRBYFLOAT`)
    to track cumulative token spend per agent and enforce strict spend rate ceilings.
    """

    # Model Pricing Table per 1,000,000 tokens (USD)
    MODEL_PRICING: Dict[str, Dict[str, float]] = {
        "gemini-2.5-flash": {"prompt": 0.075, "completion": 0.30},
        "gemini-1.5-flash": {"prompt": 0.075, "completion": 0.30},
        "gpt-4o-mini": {"prompt": 0.15, "completion": 0.60},
        "claude-3-5-haiku": {"prompt": 0.80, "completion": 4.00},
        "default": {"prompt": 0.10, "completion": 0.40}
    }

    def __init__(self, redis_client: Optional[aioredis.Redis] = None):
        self.redis_client = redis_client

    async def _get_client(self) -> aioredis.Redis:
        if self.redis_client is not None:
            return self.redis_client
        return await get_redis_client()

    @staticmethod
    def _make_spend_key(agent_id: str) -> str:
        return f"agent:{agent_id}:spend"

    @staticmethod
    def _make_tokens_key(agent_id: str) -> str:
        return f"agent:{agent_id}:tokens"

    def calculate_cost(self, prompt_tokens: int, completion_tokens: int, model: str) -> float:
        """
        Calculates exact dollar cost for a turn given prompt & completion token counts.
        """
        pricing = self.MODEL_PRICING.get(model, self.MODEL_PRICING["default"])
        prompt_cost = (prompt_tokens / 1_000_000.0) * pricing["prompt"]
        completion_cost = (completion_tokens / 1_000_000.0) * pricing["completion"]
        return prompt_cost + completion_cost

    async def record_usage_and_check(
        self,
        agent_id: str,
        prompt_tokens: int,
        completion_tokens: int,
        max_budget_usd: float,
        model: str = "gemini-2.5-flash"
    ) -> Dict[str, Any]:
        """
        Atomically increments token & spend counters in Redis and checks against budget ceiling.
        Throws BudgetExceededException if max_budget_usd is exceeded.
        """
        client = await self._get_client()
        turn_cost = self.calculate_cost(prompt_tokens, completion_tokens, model)
        total_tokens_turn = prompt_tokens + completion_tokens

        spend_key = self._make_spend_key(agent_id)
        tokens_key = self._make_tokens_key(agent_id)

        # Atomic Redis increment
        async with client.pipeline(transaction=True) as pipe:
            pipe.incrbyfloat(spend_key, turn_cost)
            pipe.incrby(tokens_key, total_tokens_turn)
            results = await pipe.execute()

        new_total_spend: float = float(results[0])
        new_total_tokens: int = int(results[1])

        summary = {
            "agent_id": agent_id,
            "turn_cost_usd": turn_cost,
            "total_spend_usd": new_total_spend,
            "total_tokens": new_total_tokens,
            "max_budget_usd": max_budget_usd,
            "budget_remaining_usd": max(0.0, max_budget_usd - new_total_spend)
        }

        if new_total_spend >= max_budget_usd:
            raise BudgetExceededException(
                agent_id=agent_id,
                current_spend_usd=new_total_spend,
                max_budget_usd=max_budget_usd
            )

        return summary

    async def get_summary(self, agent_id: str, max_budget_usd: float) -> Dict[str, Any]:
        """
        Retrieves active spend metrics for an agent from Redis without mutating counters.
        """
        client = await self._get_client()
        spend_key = self._make_spend_key(agent_id)
        tokens_key = self._make_tokens_key(agent_id)

        spend_raw = await client.get(spend_key)
        tokens_raw = await client.get(tokens_key)

        current_spend = float(spend_raw) if spend_raw is not None else 0.0
        current_tokens = int(tokens_raw) if tokens_raw is not None else 0

        return {
            "agent_id": agent_id,
            "total_spend_usd": current_spend,
            "total_tokens": current_tokens,
            "max_budget_usd": max_budget_usd,
            "budget_remaining_usd": max(0.0, max_budget_usd - current_spend)
        }

    async def reset_budget(self, agent_id: str) -> None:
        """
        Clears budget spend tracking keys for an agent.
        """
        client = await self._get_client()
        spend_key = self._make_spend_key(agent_id)
        tokens_key = self._make_tokens_key(agent_id)
        await client.delete(spend_key, tokens_key)
