"""Cooperative control for bounded, synchronous calculations; no background workers."""
from collections import Counter
import time

from companion.contracts import CompanionError, ErrorCode


class StopCalculation(Exception):
    def __init__(self, reason):
        self.reason = reason


class CalculationBudget:
    def __init__(self, limits, *, cancelled=None, clock=time.monotonic):
        self.clock = clock
        self.deadline = clock() + limits["max_seconds"]
        self.limits = {"actions": limits["max_actions"], "candidates": limits["max_candidates"]}
        self.used = Counter()
        self.cancelled = cancelled or (lambda: False)

    def checkpoint(self, kind=None):
        if self.cancelled():
            raise StopCalculation("cancelled")
        if self.clock() >= self.deadline:
            raise StopCalculation("time_budget")
        if kind:
            if kind not in self.limits:
                raise CompanionError(ErrorCode.INVALID_INPUT, "未知计算预算类型")
            if self.used[kind] >= self.limits[kind]:
                raise StopCalculation(kind + "_budget")
            self.used[kind] += 1
