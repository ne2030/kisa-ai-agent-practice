# Day 2 실습 — AICC/e-commerce Agent 운영 설계

Day 1에서 만든 단일 ReAct loop 다음 단계예요. Day 2는 고객응대 Agent를 작은 운영 시스템처럼 구성해요.

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

Day 2는 기본값으로 실제 Gemini LLM을 호출해요. `GEMINI_API_KEY`를 `.env`에 넣어야 해요. 네트워크/API 문제를 분리해서 graph·guardrail 구조만 확인할 때는 `--llm-mode mock`을 써요.

처음 10분은 커맨드만 실행하지 말고 `CODE_WALKTHROUGH.md`를 같이 열어둬요. 실행 결과 맨 아래에 `code path`가 나오고, 그 순서대로 파일을 열면 “왜 이 답이 나왔는지”를 바로 따라갈 수 있어요.

---

## 빠른 실행

```bash
# 정상 조회
python3 day2_aicc/app.py --scenario order_status

# 배송지 변경 가능 케이스
python3 day2_aicc/app.py --scenario address_change_processing

# 배송지 변경 불가 케이스
python3 day2_aicc/app.py --scenario address_change_shipped --policy cheap --guards on

# direct prompt injection
python3 day2_aicc/app.py --scenario direct_injection

# indirect prompt injection: 외부 정책 문서에 숨은 payload 포함
python3 day2_aicc/app.py --scenario indirect_policy --policy cheap --guards on

# model policy별 품질/비용 비교
python3 day2_aicc/eval_day2.py --compare-models --scenario refund_old

# safety metrics: ASR/FPR/Utility/Latency/Coverage gap
python3 day2_aicc/eval_day2.py --include-unguarded --policies cheap --llm-mode mock
```

평가 리포트는 `.eval/day2_eval_latest.md`와 `.eval/day2_eval_latest.json`에 저장돼요.

---

## 첫 실행을 코드로 따라가기

```bash
python3 day2_aicc/app.py --scenario order_status --llm-mode mock
```

이 요청은 조회형 요청이라 쓰기 action이 없어야 해요. 결과에서 볼 값과 코드 위치를 같이 봐요.

| 출력 | 코드 위치 | 왜 그렇게 나오는지 |
|---|---|---|
| `scenario: order_status` | `scenarios.py::SCENARIOS` | 실습 fixture의 메시지와 `user_id`를 가져와요. |
| `intent/order: order_status / ORD-1001` | `graph.py::triage_node()` | `_parse_intent()`가 “주문” 문구를 보고 `order_status`로 분류하고, 정규식으로 주문번호를 뽑아요. |
| `actions: (none)` | `graph.py::mock_specialist_node()` 또는 `live_llm.py::live_specialist_node()` | 주문 조회는 읽기 응답이라 `proposed_actions`가 비어 있어요. |
| `risk events` | 각 node의 `_risk()` / `append_event()` | graph가 지나온 node 기록이에요. `action_guard:no_action`이면 실행할 쓰기 tool이 없었다는 뜻이에요. |
| `cost estimate` | `model_policy.py::estimate_cost()` | system prompt/tool schema는 caching 후보로, 요청별 context는 일반 input으로 잡아 비용을 추정해요. |
| `code path` | `app.py::code_path_lines()` | 다음에 열어볼 파일 순서예요. |

더 자세한 코드 읽기 순서는 [`CODE_WALKTHROUGH.md`](./CODE_WALKTHROUGH.md)에 정리해뒀어요.

---

## LangGraph 흐름

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

LangGraph에서 볼 핵심은 세 가지예요.

- `state.py::AICCState`: 모든 node가 공유하는 상담 상태
- `graph.py::*_node()`: state를 읽고 일부 필드만 업데이트하는 함수
- `graph.py::build_graph()`: node 순서와 차단 분기 정의

`build_graph()`를 먼저 보면 LangGraph가 덜 추상적으로 보여요. framework가 알아서 흐름을 숨기는 게 아니라, 아래 코드처럼 직접 node와 edge를 등록해요.

```python
builder.add_node("triage", triage_node)
builder.add_edge("triage", "load_context")
builder.add_conditional_edges("action_guard", blocked_or_continue, ...)
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

Day 2는 명령어 실행보다 코드 구조를 읽는 시간이 더 중요해요. 요청 하나가 어떤 파일을 지나는지 먼저 확인해요.

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

중간 node 뒤에서 멈춘 뒤 같은 `thread_id`로 재개해요.

```bash
python3 day2_aicc/app.py \
  --scenario refund_recent \
  --thread-id demo-refund-1 \
  --interrupt-after retrieve_policy

python3 day2_aicc/app.py \
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
| 0–10분 | LangGraph map | `CODE_WALKTHROUGH.md` 기준으로 `StateGraph`, node, edge, checkpoint 개념 확인 |
| 10–18분 | First trace | `order_status` 실행 후 `risk events`와 `code path`를 따라 `app.py` → `graph.py` → `tools.py` 확인 |
| 18–27분 | Checkpoint | `--interrupt-after`, `--resume`, `--show-state`로 저장되는 state와 재개 위치 확인 |
| 27–39분 | Tool boundary | 배송지 변경·환불 케이스에서 `proposed_actions`와 `action_guard` 조건 수정 |
| 39–50분 | Guardrail attack | direct / indirect injection payload가 어느 layer에서 막히는지 비교하고 패턴 추가 |
| 50–57분 | Safety metrics / cost | ASR/FPR/Utility/Latency/Coverage gap + model cost + prompt caching 후보 확인 |
| 57–60분 | Mini challenge | 새 scenario 또는 eval case 하나 추가하고 리포트 변화 확인 |

---

## 필수 TODO 세트

작업량이 너무 작아지지 않도록 12개를 준비했어요. 시간이 부족하면 1–8을 필수, 9–12를 확장으로 진행해요.

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
python3 day2_aicc/app.py --scenario refund_old --policy cheap --guards on
python3 day2_aicc/app.py --scenario refund_old --policy standard --guards on
python3 day2_aicc/app.py --scenario refund_old --policy strong --guards on
```

관찰 포인트:

- cheap이 잘못된 return action을 제안하는지
- action_guard가 실행을 막는지
- cost estimate가 얼마나 차이 나는지

### 2) guardrail만 변경

```bash
python3 day2_aicc/app.py --scenario indirect_policy --policy cheap --guards off
python3 day2_aicc/app.py --scenario indirect_policy --policy cheap --guards context,action
```

관찰 포인트:

- 외부 정책 문서의 `SYSTEM OVERRIDE`가 action으로 이어지는지
- context_guard만으로 충분한지, action_guard까지 필요한지

### 3) budget policy 변경

```bash
python3 day2_aicc/app.py --scenario order_status --policy auto --budget strict
python3 day2_aicc/app.py --scenario compensation_delay --policy auto --budget strict
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

Day 1과 같은 용도로 `solutions/` checkpoint를 제공해요. Day 2는 여러 파일이 함께 바뀌므로 numbered package 형태예요.

```bash
python3 day2_aicc/solutions/step01_baseline/app.py --scenario order_status
python3 day2_aicc/solutions/step02_guardrails/app.py --scenario indirect_policy --policy cheap --guards context,action
python3 day2_aicc/solutions/step03_cost_routing/app.py --scenario compensation_delay --policy auto --budget strict
python3 day2_aicc/solutions/step04_eval_extended/eval_day2.py --compare-models
```

자세한 내용은 `day2_aicc/solutions/README.md`를 참고해요.
