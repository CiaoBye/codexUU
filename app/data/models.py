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
    cumulative: TokenBreakdown = field(default_factory=TokenBreakdown)

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


@dataclass
class TaskItem:
    id: str
    title: str
    status: str  # running, pending, scheduled, completed
    runtime: RuntimeScope = RuntimeScope.CODEX
    updated_at: Optional[datetime] = None
    project: str = ""


@dataclass
class DailyToken:
    date: datetime
    total: int = 0
    cached_input: int = 0
    uncached_input: int = 0
    output: int = 0


@dataclass
class ProjectStats:
    name: str
    token_total: int = 0
    estimated_value: float = 0.0
    thread_count: int = 0
    last_active: Optional[datetime] = None


@dataclass
class ToolUsage:
    name: str
    call_count: int = 0
    runtime: RuntimeScope = RuntimeScope.CODEX


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

    def for_scope(self, scope: RuntimeScope) -> UsageSnapshot:
        return self.codex if scope == RuntimeScope.CODEX else self.claude_code


CODEX_PROMPT_PRICES = {
    "uncached_input": 2.50,
    "cached_input": 0.30,
    "output": 10.00,
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


def format_tokens(count: int) -> str:
    if count >= 1_000_000_000:
        return f"{count / 1_000_000_000:.1f}B"
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1_000:
        return f"{count / 1_000:.1f}K"
    return str(count)


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
