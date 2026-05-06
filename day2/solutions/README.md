# Day 2 solutions

Solutions는 reference runner만 둬요. 수업 중 수정 위치는 `day2/` 본 파일이에요.

```bash
python3 day2/solutions/cost_solution.py --llm-mode mock --profile standard --prompt-style structured --out-dir /tmp/day2-cost-solution
python3 day2/solutions/cost_eval_solution.py --report /tmp/day2-cost-solution/cost_latest.json --out-dir /tmp/day2-cost-solution
python3 day2/solutions/cost_projection_solution.py --report /tmp/day2-cost-solution/cost_latest.json --cache-hit-rate 0.7 --batch-ratio 0.5 --out-dir /tmp/day2-cost-solution
python3 day2/solutions/security_solution.py --llm-mode mock --mode guarded --out-dir /tmp/day2-security-solution
```

수정해볼 곳:

- `prompts.py`
- `cost_golden_set.yaml`
- `model_catalog.py`
- `security_controls.py`
