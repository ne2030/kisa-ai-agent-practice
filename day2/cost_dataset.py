"""2일차 비용 평가 실습용 기준 케이스."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

DATASET_PATH = Path(__file__).with_name("cost_golden_set.yaml")


def load_cost_cases(path: str | Path = DATASET_PATH) -> list[dict[str, Any]]:
    cases = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(cases, list):
        raise ValueError(f"cost golden set must be a list: {path}")
    return cases


def get_cost_case(case_id: str, path: str | Path = DATASET_PATH) -> dict[str, Any]:
    cases = load_cost_cases(path)
    for case in cases:
        if case.get("id") == case_id:
            return case
    known = ", ".join(str(case.get("id")) for case in cases)
    raise ValueError(f"unknown cost case: {case_id}. choose one of: {known}")


def default_case_id() -> str:
    cases = load_cost_cases()
    if not cases:
        raise ValueError("cost golden set is empty")
    return str(cases[0]["id"])
