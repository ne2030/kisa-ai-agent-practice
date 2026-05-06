# Day 2 solutions

Day 2는 실습 코드 자체가 작아서 solutions는 같은 runner를 바로 호출하는 reference entrypoint만 둬요.

```bash
python3 day2/solutions/cost_solution.py --llm-mode mock --out-dir /tmp/day2-cost-solution
python3 day2/solutions/security_solution.py --llm-mode mock --mode guarded --out-dir /tmp/day2-security-solution
```

수업 중 수정 위치는 본 파일이 아니라 아래 파일이에요.

- `prompts.py`
- `model_catalog.py`
- `security_controls.py`
