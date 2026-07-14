from __future__ import annotations
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional


class RuntimeScope(Enum):
    CODEX = "codex"
    CLAUDE_CODE = "claudeCode"


@dataclass
class QuotaInfo:
    used_pct: float
    remaining_pct: float
    reset_time: Optional[datetime] = None


@dataclass
class TokenBreakdown:
    cached_input: int = 0
    uncached_input: int = 0
    output: int = 0

    @property
    def total(self) -> int:
        return self.cached_input + self.uncached_input + self.output

    @property
    def input_total(self) -> int:
        return self.cached_input + self.uncached_input


@dataclass
class TokenStats:
    today: TokenBreakdown = field(default_factory=TokenBreakdown)
    last_7d: TokenBreakdown = field(default_factory=TokenBreakdown)
    current_week: TokenBreakdown = field(default_factory=TokenBreakdown)
    cumulative: TokenBreakdown = field(default_factory=TokenBreakdown)
    current_month: TokenBreakdown = field(default_factory=TokenBreakdown)

    @property
    def today_total(self) -> int:
        return self.today.total

    @property
    def last_7d_total(self) -> int:
        return self.last_7d.total


@dataclass
class UsageSnapshot:
    quota_5h: Optional[QuotaInfo] = None
    quota_7d: Optional[QuotaInfo] = None
    tokens: TokenStats = field(default_factory=TokenStats)
    api_equivalent_value: float = 0.0
    today_api_equivalent_value: float = 0.0
    last_7d_api_equivalent_value: float = 0.0
    current_week_api_equivalent_value: float = 0.0
    monthly_api_equivalent_value: float = 0.0
    pricing_coverage_pct: float = 0.0
    unpriced_token_total: int = 0
    cumulative_index_total: Optional[int] = None


@dataclass
class TaskItem:
    id: str
    title: str
    status: str  # running, pending, scheduled, completed
    runtime: RuntimeScope = RuntimeScope.CODEX
    updated_at: Optional[datetime] = None
    project: str = ""
    detail: str = ""
    thread_count: int = 1


@dataclass
class DailyToken:
    date: datetime
    total: int = 0
    cached_input: int = 0
    uncached_input: int = 0
    output: int = 0
    runtime: RuntimeScope = RuntimeScope.CODEX


@dataclass
class ProjectStats:
    name: str
    token_total: int = 0
    estimated_value: float = 0.0
    thread_count: int = 0
    last_active: Optional[datetime] = None
    runtime: RuntimeScope = RuntimeScope.CODEX
    last_7d_token_total: Optional[int] = None
    last_7d_estimated_value: Optional[float] = None
    current_week_token_total: Optional[int] = None
    current_week_estimated_value: Optional[float] = None
    current_week_pricing_coverage_pct: float = 0.0
    current_month_token_total: Optional[int] = None
    current_month_estimated_value: Optional[float] = None
    current_month_pricing_coverage_pct: float = 0.0
    pricing_coverage_pct: float = 0.0
    source_label: str = ""
    model_usage: list["ModelUsage"] = field(default_factory=list)
    sessions: list["SessionUsage"] = field(default_factory=list)


@dataclass
class ModelUsage:
    name: str
    token_total: int = 0
    estimated_value: float = 0.0
    pricing_coverage_pct: float = 0.0
    effort: str = ""
    runtime: RuntimeScope = RuntimeScope.CODEX
    tokens: TokenBreakdown = field(default_factory=TokenBreakdown)
    session_count: int = 0
    turn_count: int = 0
    last_active: Optional[datetime] = None
    daily_tokens: list[DailyToken] = field(default_factory=list)
    session_activity: dict[str, datetime] = field(default_factory=dict)
    turn_activity: dict[str, datetime] = field(default_factory=dict)


@dataclass
class SessionUsage:
    session_id: str
    token_total: int = 0
    last_active: Optional[datetime] = None
    model: str = ""


@dataclass
class ToolUsage:
    name: str
    call_count: int = 0
    runtime: RuntimeScope = RuntimeScope.CODEX
    category: str = ""
    estimated_value: float = 0.0


@dataclass
class SkillUsage:
    name: str
    use_count: int = 0
    runtime: RuntimeScope = RuntimeScope.CODEX


@dataclass
class MultiRuntimeUsageSnapshot:
    codex: UsageSnapshot = field(default_factory=UsageSnapshot)
    claude_code: UsageSnapshot = field(default_factory=UsageSnapshot)
    tasks: list[TaskItem] = field(default_factory=list)
    daily_tokens: list[DailyToken] = field(default_factory=list)
    projects: list[ProjectStats] = field(default_factory=list)
    tools: list[ToolUsage] = field(default_factory=list)
    skills: list[SkillUsage] = field(default_factory=list)
    models: list[ModelUsage] = field(default_factory=list)

    def for_scope(self, scope: RuntimeScope) -> UsageSnapshot:
        return self.codex if scope == RuntimeScope.CODEX else self.claude_code


CODEX_PROMPT_PRICES = {
    "uncached_input": 5.00,
    "cached_input": 0.50,
    "output": 30.00,
}

# OpenAI standard API prices per 1M text tokens. Unknown/internal/third-party
# model identifiers are intentionally left unpriced instead of borrowing a
# different model's rate.
OPENAI_MODEL_PRICES = {
    "gpt-5.6-sol": {"uncached_input": 5.00, "cached_input": 0.50, "output": 30.00},
    "gpt-5.6": {"uncached_input": 5.00, "cached_input": 0.50, "output": 30.00},
    "gpt-5.6-terra": {"uncached_input": 2.50, "cached_input": 0.25, "output": 15.00},
    "gpt-5.6-luna": {"uncached_input": 1.00, "cached_input": 0.10, "output": 6.00},
    "gpt-5.5": {"uncached_input": 5.00, "cached_input": 0.50, "output": 30.00},
    "gpt-5.4": {"uncached_input": 2.50, "cached_input": 0.25, "output": 15.00},
    "gpt-5.4-mini": {"uncached_input": 0.75, "cached_input": 0.075, "output": 4.50},
    "gpt-5": {"uncached_input": 1.25, "cached_input": 0.125, "output": 10.00},
    "gpt-5-codex": {"uncached_input": 1.25, "cached_input": 0.125, "output": 10.00},
    "gpt-5-mini": {"uncached_input": 0.25, "cached_input": 0.025, "output": 2.00},
    "gpt-5-nano": {"uncached_input": 0.05, "cached_input": 0.005, "output": 0.40},
}

# Current official pay-as-you-go USD prices per 1M tokens.  Provider model
# identifiers must match exactly before a price is applied; private gateway
# aliases remain unpriced.
THIRD_PARTY_MODEL_PRICES = {
    "deepseek-v4-flash": {"uncached_input": 0.14, "cached_input": 0.0028, "output": 0.28},
    "deepseek-v4-pro": {"uncached_input": 0.435, "cached_input": 0.003625, "output": 0.87},
    "mimo-v2.5": {"uncached_input": 0.14, "cached_input": 0.0028, "output": 0.28},
    "mimo-v2.5-pro": {"uncached_input": 0.435, "cached_input": 0.0036, "output": 0.87},
}

MODEL_PRICE_SOURCES = {
    "OpenAI": "https://openai.com/api/pricing/",
    "DeepSeek": "https://api-docs.deepseek.com/quick_start/pricing",
    "Xiaomi MiMo": "https://mimo.mi.com/docs/zh-CN/price/pay-as-you-go",
}

CLAUDE_PROMPT_PRICES = {
    "uncached_input": 3.00,
    "cached_input": 0.30,
    "output": 15.00,
}

MODEL_MIX = {
    "uncached_input_pct": 0.30,
    "cached_input_pct": 0.50,
    "output_pct": 0.20,
}

MILLION = 1_000_000
FULL_MONTHLY_VALUE = 46500.0


def estimate_api_value(
    tokens: TokenBreakdown,
    prices: Optional[dict[str, float]] = None,
) -> float:
    p = prices or CODEX_PROMPT_PRICES
    value = (
        tokens.uncached_input / MILLION * p["uncached_input"]
        + tokens.cached_input / MILLION * p["cached_input"]
        + tokens.output / MILLION * p["output"]
    )
    return round(value, 2)


def prices_for_model(model: str) -> Optional[dict[str, float]]:
    normalized = str(model or "").strip().lower()
    if not normalized:
        return None
    if normalized in OPENAI_MODEL_PRICES:
        return OPENAI_MODEL_PRICES[normalized]
    if normalized in THIRD_PARTY_MODEL_PRICES:
        return THIRD_PARTY_MODEL_PRICES[normalized]
    # Snapshot suffixes keep the base model's published price.
    for model_id in sorted(OPENAI_MODEL_PRICES, key=len, reverse=True):
        if normalized.startswith(model_id + "-"):
            return OPENAI_MODEL_PRICES[model_id]
    return None


def model_provider(model: str) -> str:
    normalized = str(model or "").strip().lower()
    if normalized.startswith("gpt-") or normalized.startswith("o") or normalized.startswith("codex-"):
        return "OpenAI"
    if normalized.startswith("deepseek-"):
        return "DeepSeek"
    if normalized.startswith("mimo-"):
        return "Xiaomi MiMo"
    return "Unknown"


def is_gpt_model(model: str) -> bool:
    return str(model or "").strip().lower().startswith("gpt-")


def pricing_source_for_model(model: str) -> Optional[str]:
    return MODEL_PRICE_SOURCES.get(model_provider(model)) if prices_for_model(model) else None


def estimate_model_api_value(tokens: TokenBreakdown, model: str) -> Optional[float]:
    prices = prices_for_model(model)
    return estimate_api_value(tokens, prices) if prices else None


def format_tokens(count: int) -> str:
    sign = "-" if count < 0 else ""
    value = float(abs(count))
    units = ((1_000_000_000, "B"), (1_000_000, "M"), (1_000, "K"))
    for index, (divisor, suffix) in enumerate(units):
        next_divisor = units[index - 1][0] if index > 0 else None
        rounded = round(value / divisor, 1)
        if value >= divisor or (next_divisor and rounded >= 1000):
            if rounded >= 1000 and next_divisor:
                return f"{sign}{value / next_divisor:.1f}{units[index - 1][1]}"
            return f"{sign}{rounded:.1f}{suffix}"
    return f"{sign}{int(value)}"


def format_duration(delta: timedelta) -> str:
    total_seconds = int(delta.total_seconds())
    if total_seconds <= 0:
        return "0m"
    hours, remainder = divmod(total_seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def parse_jsonl_line(line: str) -> Optional[dict]:
    line = line.strip()
    if not line:
        return None
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return None
