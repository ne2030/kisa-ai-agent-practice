# KISA AI Agent Practice — Course Guide

이 문서는 전체 실습 안내예요. 세부 진행안은 각 Day 폴더의 guide를 써요.

---

## Day 구성

| Day | 자료 | 목표 |
|---|---|---|
| Day 1 | `day1/INSTRUCTOR_GUIDE.md` | 단일 ReAct loop, tool 추가, Langfuse trace, failure diagnosis, golden set |
| Day 2 | `day2/INSTRUCTOR_GUIDE.md` | 모델 비용 비교, golden eval, 월간 projection, security guardrail before/after |

---

## 추천 흐름

### Day 1

1. `day1/agent.py` baseline 실행
2. tool 추가
3. nested trace 확인
4. failure case 진단
5. `day1/evaluate.py`로 golden set 평가

### Day 2

1. `cost_lab.py`를 `--profile cheap`, `--profile standard`, `--profile strong` 순서로 하나씩 실행
2. `cost_eval.py`로 golden dataset 기준 품질 점수 확인
3. `cost_projection.py`로 월간 비용, prompt caching, batch 비율 확인
4. `python3 day2/security_lab.py --mode both`로 baseline/guarded 비교
5. `security_controls.py`의 TODO 수정
6. reports markdown으로 전후 차이 확인

---

## 공통 설치 확인

```bash
pip install -r requirements.txt
python3 day2/cost_lab.py --profile cheap --prompt-style structured
python3 day2/cost_eval.py --report day2/reports/cost_latest.json
python3 day2/cost_projection.py --report day2/reports/cost_latest.json
python3 day2/security_lab.py --mode guarded
```

Day 1은 Gemini/Langfuse key가 필요해요.
Day 2는 Gemini key로 live 실행해요. mock은 네트워크나 quota 문제가 있을 때만 fallback으로 써요.

---

## 시간 배분 예시

| 세션 | 시간 | 내용 |
|---|---:|---|
| Day 1 | 60분 | 단일 Agent loop + observability + evaluation |
| Day 2 | 60분 | Cost 비교/eval/projection + Security guardrail |
