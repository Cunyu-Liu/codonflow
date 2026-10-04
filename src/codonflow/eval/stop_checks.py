"""Stop-condition assertions (spec R6-7) coded as runtime checks."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Optional


@dataclass
class StopThresholds:
    feasible_sample_rate_min: float = 0.01
    frame_break_rate_max: float = 0.05
    ned_vs_baseline_min_ratio: float = 0.70
    cost_vs_lineardesign_max_ratio: float = 5.0


class StopConditionChecker:
    """Five pre-registered stop conditions; any trigger must be archived."""

    def __init__(self, thresholds: Optional[StopThresholds] = None,
                 on_trigger: Optional[Callable[[str, Dict], None]] = None):
        self.t = thresholds or StopThresholds()
        self.on_trigger = on_trigger
        self.triggered: Dict[str, Dict] = {}

    def check_feasible_rate(self, rate: float) -> bool:
        if rate < self.t.feasible_sample_rate_min:
            self._fire("cond1_feasible_rate", {"rate": rate})
            return True
        return False

    def check_frame_break(self, rate: float) -> bool:
        if rate > self.t.frame_break_rate_max:
            self._fire("cond2_frame_break", {"rate": rate})
            return True
        return False

    def check_reference_table(self, improvement_kept: bool, detail: Dict) -> bool:
        if not improvement_kept:
            self._fire("cond3_reference_table", detail)
            return True
        return False

    def check_cost(self, cost_ratio: float) -> bool:
        if cost_ratio > self.t.cost_vs_lineardesign_max_ratio:
            self._fire("cond4_cost", {"ratio": cost_ratio})
            return True
        return False

    def check_ned(self, ned, baseline_ned) -> bool:
        if baseline_ned <= 0:
            return False
        if ned < self.t.ned_vs_baseline_min_ratio * baseline_ned:
            self._fire("cond5_mode_collapse", {"ned": ned, "baseline": baseline_ned})
            return True
        return False

    def _fire(self, name: str, detail: Dict) -> None:
        self.triggered[name] = detail
        if self.on_trigger:
            self.on_trigger(name, detail)
