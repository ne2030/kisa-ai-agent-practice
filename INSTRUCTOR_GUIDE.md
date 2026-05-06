# KISA AI Agent Practice — Course Guide

이 문서는 전체 실습 안내입니다. 세부 진행안은 각 Day 폴더의 guide를 사용합니다.

---

## Day 구성

| Day | 자료 | 목표 |
|---|---|---|
| Day 1 | `day1/INSTRUCTOR_GUIDE.md` | 단일 ReAct loop, tool 추가, Langfuse trace, failure diagnosis, golden set |
| Day 2 | `day2_aicc/INSTRUCTOR_GUIDE.md` | LangGraph AICC Agent, checkpoint, guardrails, model/cost 비교 |

---

## 추천 흐름

### Day 1

1. `day1/agent.py` baseline 실행
2. tool 추가
3. nested trace 확인
4. failure case 진단
5. `day1/evaluate.py`로 golden set 평가

### Day 2

1. `day2_aicc.app`로 주문 조회/배송지 변경/환불/보상 scenario 실행
2. LangGraph checkpoint 중단/재개 확인
3. direct / indirect prompt injection 비교
4. action_guard로 쓰기 tool boundary 확인
5. `day2_aicc.eval_day2`로 cheap/standard/strong 품질·비용 비교
6. prompt caching 후보와 batch 적용 위치 토론

---

## 공통 설치 확인

```bash
pip install -r requirements.txt
python -m day2_aicc.app --scenario order_status
```

Day 1은 Gemini/Langfuse key가 필요합니다.
Day 2는 기본값으로 실제 Gemini LLM을 호출하므로 `GEMINI_API_KEY`가 필요합니다. 네트워크/API 문제를 분리해서 graph만 볼 때는 `--llm-mode mock`을 씁니다.

---

## 시간 배분 예시

| 세션 | 시간 | 내용 |
|---|---:|---|
| Day 1 | 60분 | 단일 Agent loop + observability + evaluation |
| Day 2 | 60분 | AICC graph + checkpoint + guardrails + cost lab |

Day 2는 TODO가 많은 편입니다. 전체를 다 끝내는 방식보다, 조별로 TODO를 나눠서 마지막 5분에 결과를 공유하는 방식이 좋습니다.
