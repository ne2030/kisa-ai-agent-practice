# Day 2 실습 — AICC/e-commerce Agent 운영 설계

Day 1에서 만든 단일 ReAct loop 다음 단계입니다. Day 2는 고객응대 Agent를 작은 운영 시스템처럼 구성합니다.

- LangGraph `StateGraph`로 상담 흐름 분리
- SQLite checkpoint로 중단/재개 확인
- 주문 조회, 배송지 변경, 취소/환불, 지연 보상 tool 연결
- direct / indirect prompt injection 방어
- model policy별 품질·비용 비교
- prompt caching / batch 추정값 확인

---

## 작업 위치

```bash
cd kisa-ai-agent-practice
pip install -r requirements.txt
```

Day 2는 기본값으로 실제 Gemini LLM을 호출합니다. `GEMINI_API_KEY`를 `.env`에 넣어야 합니다. 네트워크/API 문제를 분리해서 graph·guardrail 구조만 확인할 때는 `--llm-mode mock`을 사용합니다.

---

## 빠른 실행

```bash
# 정상 조회
python -m day2_aicc.app --scenario order_status

# 배송지 변경 가능 케이스
python -m day2_aicc.app --scenario address_change_processing

# 배송지 변경 불가 케이스
python -m day2_aicc.app --scenario address_change_shipped --policy cheap --guards on

# direct prompt injection
python -m day2_aicc.app --scenario direct_injection

# indirect prompt injection: 외부 정책 문서에 숨은 payload 포함
python -m day2_aicc.app --scenario indirect_policy --policy cheap --guards on

# model policy별 품질/비용 비교
python -m day2_aicc.eval_day2 --compare-models --scenario refund_old

# safety metrics: ASR/FPR/Utility/Latency/Coverage gap
python -m day2_aicc.eval_day2 --include-unguarded --policies cheap --llm-mode mock
```

평가 리포트는 `.eval/day2_eval_latest.md`와 `.eval/day2_eval_latest.json`에 저장됩니다.

---

## Graph 흐름

```text
input_guard
  -> triage
  -> load_context
  -> retrieve_policy
  -> context_guard
  -> specialist
  -> action_guard
  -> execute_action
  -> final_review
```

레이어별 역할:

| layer | 역할 | 막는 것 | 못 막는 것 |
|---|---|---|---|
| input_guard | 사용자 입력의 직접 공격 탐지 | `ignore previous`, system prompt 탈취 요청 | 외부 문서에 숨어 들어온 payload |
| context_guard | RAG/정책 문서의 instruction-like payload 제거 | 외부 CMS, HTML comment payload | 정상 문서처럼 보이는 정책 충돌 전부 |
| action_guard | 실제 tool 실행 전 정책 검증 | shipped 배송지 변경, 14일 초과 환불, 과도한 쿠폰 | 읽기 전용 답변의 품질 문제 |
| checkpoint | node 단위 상태 저장 | 중간 실패 후 재개 | 잘못 저장된 state 설계 |
| eval | golden case 반복 실행 | regression, model 변경 영향 | golden set 밖의 실제 사용자 다양성 |

---

## 코드 구조 먼저 보기

Day 2는 명령어 실행보다 코드 구조를 읽는 시간이 더 중요합니다. 요청 하나가 어떤 파일을 지나는지 먼저 확인합니다.

| 파일 | 역할 | 읽을 위치 |
|---|---|---|
| `app.py` | CLI 옵션을 읽고 초기 `AICCState` 생성 | `make_initial_state`, `main` |
| `state.py` | graph node가 공유하는 state schema | `AICCState` |
| `graph.py` | LangGraph node/edge 정의 | `build_graph`, `specialist_node` |
| `live_llm.py` | Gemini 호출과 JSON action proposal | `live_specialist_node` |
| `guardrails.py` | input/context/action guardrail | `input_guard_node`, `sanitize_policy_docs`, `action_guard_node` |
| `tools.py` | 주문 조회/배송지 변경/환불/쿠폰 mock tool | `TOOL_REGISTRY` |
| `model_policy.py` | model routing, prompt caching/batch 비용 추정 | `route_model_for_intent`, `estimate_cost` |
| `eval_day2.py` | golden case와 safety metrics | `EVAL_CASES`, `summarize_safety_metrics` |

추천 확인 명령:

```bash
sed -n '1,140p' day2_aicc/app.py
sed -n '1,130p' day2_aicc/state.py
sed -n '350,430p' day2_aicc/graph.py
sed -n '1,120p' day2_aicc/guardrails.py
```

---

## Checkpoint 실습

중간 node 뒤에서 멈춘 뒤 같은 `thread_id`로 재개합니다.

```bash
python -m day2_aicc.app \
  --scenario refund_recent \
  --thread-id demo-refund-1 \
  --interrupt-after retrieve_policy

python -m day2_aicc.app \
  --resume \
  --thread-id demo-refund-1
```

확인 포인트:

- `retrieve_policy`까지 실행된 state가 SQLite checkpoint에 남는지
- resume 시 `context_guard`부터 이어지는지
- checkpoint에 저장할 state가 너무 커지면 비용/보안 측면에서 어떤 문제가 생기는지

---

## 60분 진행안

| 시간 | 파트 | 실습 내용 |
|---:|---|---|
| 0–8분 | Code map | `app.py` → `state.py` → `graph.py` 흐름 확인 |
| 8–15분 | Baseline trace | 조회 요청과 쓰기 action 요청의 trace 차이 비교 |
| 15–23분 | Checkpoint | state 저장/재개, `--show-state`로 저장 내용 확인 |
| 23–34분 | Tool boundary | 배송지 변경·환불 guard 조건 수정 |
| 34–45분 | Guardrail attack | direct / indirect injection payload와 layer별 차단 비교 |
| 45–55분 | Safety metrics / cost | ASR/FPR/Utility/Latency/Coverage gap + model cost 확인 |
| 55–60분 | Mini challenge | 새 scenario + eval case 추가, 리포트 공유 |

---

## 필수 TODO 세트

작업량이 너무 작아지지 않도록 12개를 준비했습니다. 시간이 부족하면 1–8을 필수, 9–12를 확장으로 진행합니다.

### A. Graph / routing

1. `graph.py`의 `TODO-D2-01` — `교환`, `분실`, `부분 취소` 중 하나를 새 intent로 추가
2. `graph.py`의 `TODO-D2-02` — 다른 고객 주문 조회 실패 scenario 추가
3. `graph.py`의 `TODO-D2-03` — strict budget에서 policy doc 수를 줄였을 때 pass/fail 변화 기록
4. `graph.py`의 `TODO-D2-04` — cheap model이 shipped 주문에 잘못 action 제안하는 부분 수정
5. `graph.py`의 `TODO-D2-05` — 보상 쿠폰 앞에 human approval node 추가 설계 또는 구현

### B. Cost / model policy

6. `model_policy.py`의 `TODO-D2-06` — `auto` routing 정책 수정: 조회는 cheap, 금전성 action은 standard/strong
7. `eval_day2.py` 실행 결과에서 `cheap`, `standard`, `strong`의 pass/quality/cost 차이 설명
8. prompt caching 후보(stable system prompt + tool schema)와 batch 후보(golden set 평가)를 리포트에 한 줄 추가

### C. Guardrails

9. `guardrails.py`의 `TODO-D2-07` — direct injection 한국어 패턴 추가
10. `guardrails.py`의 `TODO-D2-08` — indirect payload 패턴 추가
11. `guardrails.py`의 `TODO-D2-09` — 배송지 변경 조건 강화: processing + 송장번호 없음
12. `guardrails.py`의 `TODO-D2-10`, `eval_day2.py`의 `TODO-D2-11` — 보상 정책 edge case 추가

---

## 비교 실험 예시

### 1) 모델만 변경

```bash
python -m day2_aicc.app --scenario refund_old --policy cheap --guards on
python -m day2_aicc.app --scenario refund_old --policy standard --guards on
python -m day2_aicc.app --scenario refund_old --policy strong --guards on
```

관찰 포인트:

- cheap이 잘못된 return action을 제안하는지
- action_guard가 실행을 막는지
- cost estimate가 얼마나 차이 나는지

### 2) guardrail만 변경

```bash
python -m day2_aicc.app --scenario indirect_policy --policy cheap --guards off
python -m day2_aicc.app --scenario indirect_policy --policy cheap --guards context,action
```

관찰 포인트:

- 외부 정책 문서의 `SYSTEM OVERRIDE`가 action으로 이어지는지
- context_guard만으로 충분한지, action_guard까지 필요한지

### 3) budget policy 변경

```bash
python -m day2_aicc.app --scenario order_status --policy auto --budget strict
python -m day2_aicc.app --scenario compensation_delay --policy auto --budget strict
```

관찰 포인트:

- 조회성 intent와 금전성 intent가 같은 모델을 써도 되는지
- strict budget이 context 누락을 만들 가능성

---

## 파일 맵

| 파일 | 용도 |
|---|---|
| `app.py` | 단일 scenario 실행 CLI |
| `eval_day2.py` | golden set 평가 + safety metrics + model/cost 비교 |
| `graph.py` | LangGraph node/edge 정의 |
| `guardrails.py` | input/context/action guardrail 구현 |
| `model_policy.py` | cheap/standard/strong 비용·품질 profile |
| `mock_data.py` | 주문, 고객, 배송, 정책 mock data |
| `tools.py` | 주문 조회, 배송지 변경, 환불, 쿠폰 tool |
| `scenarios.py` | 수업용 scenario fixture |
| `checkpoints/` | SQLite checkpoint 저장 위치 |
| `solutions/` | 단계별 checkpoint 패키지 |

---

## Solutions

Day 1과 같은 용도로 `solutions/` checkpoint를 제공합니다. Day 2는 여러 파일이 함께 바뀌므로 numbered package 형태입니다.

```bash
python -m day2_aicc.solutions.step01_baseline.app --scenario order_status
python -m day2_aicc.solutions.step02_guardrails.app --scenario indirect_policy --policy cheap --guards context,action
python -m day2_aicc.solutions.step03_cost_routing.app --scenario compensation_delay --policy auto --budget strict
python -m day2_aicc.solutions.step04_eval_extended.eval_day2 --compare-models
```

자세한 내용은 `day2_aicc/solutions/README.md`를 참고합니다.
