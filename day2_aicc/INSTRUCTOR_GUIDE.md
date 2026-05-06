# Day 2 Guide — AICC/e-commerce Agent

Day 1에서는 `agent.py` 하나 안에서 ReAct loop가 어떻게 도는지 봤습니다. Day 2에서는 같은 아이디어를 고객응대 서비스 흐름으로 나눠 봅니다. 핵심은 “답변 생성” 하나가 아니라, 상태 관리, tool action, guardrail, model routing, checkpoint, evaluation이 같이 돌아가는 구조를 보는 것입니다.

---

## 먼저 보는 전체 그림

```text
사용자 요청
  -> input_guard
  -> triage
  -> load_context
  -> retrieve_policy
  -> context_guard
  -> specialist_live_llm
  -> action_guard
  -> execute_action
  -> final_review
  -> eval_day2 report
```

이 흐름에서 각 파일이 맡는 역할은 다음과 같습니다.

| 파일 | 먼저 볼 함수/데이터 | 확인할 내용 |
|---|---|---|
| `app.py` | `make_initial_state`, `main` | CLI 입력이 LangGraph state로 들어가는 방식 |
| `state.py` | `AICCState` | graph 전체에서 공유하는 state 필드 |
| `scenarios.py` | `SCENARIOS` | 실습 요청 문장과 공격 케이스 |
| `mock_data.py` | `ORDERS`, `POLICY_DOCS` | 주문/배송/정책 mock 데이터 |
| `tools.py` | `TOOL_REGISTRY` | 읽기 tool과 쓰기 tool 구분 |
| `graph.py` | `build_graph`, `specialist_node` | node 순서, conditional edge, LLM 호출 위치 |
| `live_llm.py` | `live_specialist_node` | Gemini 호출과 JSON action proposal |
| `guardrails.py` | `input_guard_node`, `sanitize_policy_docs`, `action_guard_node` | direct/context/action layer별 차단 |
| `model_policy.py` | `route_model_for_intent`, `estimate_cost` | cheap/standard/strong routing과 비용 추정 |
| `eval_day2.py` | `EVAL_CASES`, `summarize_safety_metrics` | golden case, ASR/FPR/Utility/Latency/Coverage gap |

실습 시간은 명령어만 실행하는 시간이 아닙니다. 각 구간에서 **코드 위치 확인 → 실행 → 결과 비교 → TODO 수정** 순서로 진행합니다.

---

## 준비

```bash
git stash
git pull
pip install -r requirements.txt
```

Day 2 기본값은 실제 Gemini LLM 호출입니다. `.env`에 `GEMINI_API_KEY`가 필요합니다.

```bash
python3 day2_aicc/app.py --scenario order_status
```

API key나 네트워크 문제를 분리해서 구조만 확인할 때는 mock mode를 씁니다.

```bash
python3 day2_aicc/app.py --scenario order_status --llm-mode mock
```

정상 출력에서 볼 것:

- `intent/order`: 요청이 어떤 업무로 분류됐는지
- `model/guards`: 어떤 model policy와 guard mode가 적용됐는지
- `actions`: 실제 쓰기 tool이 실행됐는지
- `risk events`: 어느 layer를 통과하거나 차단됐는지
- `cost estimate`: prompt caching / batch 비교에 사용할 비용 추정값

---

## 0–8분 · 코드 구조부터 잡기

먼저 실행하지 말고, 요청 하나가 어떤 파일을 지나가는지 확인합니다.

```bash
sed -n '1,140p' day2_aicc/app.py
sed -n '1,130p' day2_aicc/state.py
sed -n '350,430p' day2_aicc/graph.py
```

볼 것:

- `app.py`가 CLI 옵션을 읽고 `AICCState`를 만드는 방식
- `state.py`에 `message`, `intent`, `order`, `policy_docs`, `proposed_actions`, `blocked_by`가 함께 들어있는 이유
- `graph.py`의 `build_graph()`에서 node 순서가 고정되고, 차단 여부에 따라 `final_review`로 빠지는 구조

질문:

- Day 1의 `contents` list와 Day 2의 `AICCState`는 어떤 점이 비슷한가?
- 왜 답변 문자열만 저장하면 안 되고, `proposed_actions`, `blocked_by`, `risk_events`까지 state에 남겨야 할까?

---

## 8–15분 · Baseline run + trace 읽기

```bash
python3 day2_aicc/app.py --scenario order_status
python3 day2_aicc/app.py --scenario address_change_processing
```

결과에서 볼 것:

- `order_status`는 읽기 응답이라 `actions`가 비어 있음
- `address_change_processing`은 쓰기 tool인 `update_shipping_address`가 실행됨
- 같은 고객응대라도 “조회”와 “변경”의 위험도가 다름

코드 위치:

```bash
sed -n '80,160p' day2_aicc/graph.py
sed -n '1,140p' day2_aicc/tools.py
```

작업:

- `tools.py`에서 읽기 tool과 쓰기 tool을 나눠 표시해 봅니다.
- `graph.py`의 `tool_trace`가 어떤 순서로 쌓이는지 확인합니다.

---

## 15–23분 · Checkpoint와 state 복구

```bash
python3 day2_aicc/app.py \
  --scenario refund_recent \
  --thread-id demo-refund \
  --interrupt-after retrieve_policy

python3 day2_aicc/app.py \
  --resume \
  --thread-id demo-refund
```

결과에서 볼 것:

- 첫 번째 실행은 `retrieve_policy` 뒤에서 멈춤
- resume 시 `context_guard`부터 이어짐
- 같은 `thread_id`가 상담 세션 키처럼 동작함

코드 위치:

```bash
sed -n '130,180p' day2_aicc/app.py
sed -n '385,430p' day2_aicc/graph.py
```

작업:

- `--show-state`를 붙여서 checkpoint에 남는 state 크기와 민감정보를 확인합니다.
- state에 원문 개인정보나 긴 RAG context를 그대로 남기는 것이 왜 위험한지 적어 봅니다.

---

## 23–34분 · Tool boundary 수정

먼저 위험한 비교를 실행합니다.

```bash
python3 day2_aicc/app.py --scenario address_change_shipped --policy cheap --guards on --llm-mode mock
python3 day2_aicc/app.py --scenario address_change_shipped --policy cheap --guards off --llm-mode mock
python3 day2_aicc/app.py --scenario refund_old --policy cheap --guards on --llm-mode mock
python3 day2_aicc/app.py --scenario refund_old --policy cheap --guards off --llm-mode mock
```

결과에서 볼 것:

- `guards=off`에서는 모델이 잘못 제안한 action이 실행될 수 있음
- `action_guard`는 tool 실행 직전의 마지막 방어선
- 좋은 구조는 모델이 틀려도 host application이 위험한 action을 막는 구조

코드 위치:

```bash
sed -n '190,260p' day2_aicc/graph.py
sed -n '120,175p' day2_aicc/guardrails.py
```

작업:

- `TODO-D2-04`: shipped 주문에 대해 cheap profile이 잘못 action을 제안하는 부분을 수정합니다.
- `TODO-D2-09`: 배송지 변경 가능 조건을 `processing + 송장번호 없음`으로 강화합니다.
- 수정 후 `guards=off`에서도 더 안전해졌는지 다시 비교합니다.

---

## 34–45분 · Direct / indirect prompt injection

Direct injection:

```bash
python3 day2_aicc/app.py --scenario direct_injection --guards on
python3 day2_aicc/app.py --scenario direct_injection --guards off
```

Indirect injection:

```bash
python3 day2_aicc/app.py --scenario indirect_policy --policy cheap --guards off --llm-mode mock
python3 day2_aicc/app.py --scenario indirect_policy --policy cheap --guards context,action --llm-mode mock
```

공격 흐름:

```text
외부 FAQ/CMS 문서
  -> retrieve_policy
  -> 모델이 문서 속 instruction을 정책으로 착각
  -> issue_coupon 같은 쓰기 tool 제안
  -> action_guard 없으면 실제 실행
```

코드 위치:

```bash
sed -n '1,120p' day2_aicc/guardrails.py
sed -n '130,170p' day2_aicc/tools.py
sed -n '120,180p' day2_aicc/mock_data.py
```

작업:

- `TODO-D2-07`: 한국어 direct injection 패턴을 추가합니다.
- `TODO-D2-08`: HTML comment, markdown link, base64 힌트 같은 indirect payload 패턴을 추가합니다.
- context guard만 켠 경우와 context+action guard를 같이 켠 경우를 비교합니다.

---

## 45–55분 · Safety metrics / model cost

```bash
python3 day2_aicc/eval_day2.py --compare-models --llm-mode mock
python3 day2_aicc/eval_day2.py --include-unguarded --policies cheap --llm-mode mock
cat .eval/day2_eval_latest.md
```

리포트에서 볼 것:

- **ASR**: injection이 실제 action으로 이어진 비율
- **FPR**: 정상 요청이 guardrail에 잘못 막힌 비율
- **Utility**: guardrail 적용 후 정상 업무 성공률 유지 여부
- **Latency tax**: guardrail on/off p95 지연 차이
- **Coverage gap**: 아직 dataset에 없는 위험 카테고리
- **Cost / batch cost**: 실시간 요청과 오프라인 평가 비용 차이

코드 위치:

```bash
sed -n '1,120p' day2_aicc/model_policy.py
sed -n '1,210p' day2_aicc/eval_day2.py
```

작업:

- `TODO-D2-06`: `auto` routing 정책을 수정합니다.
  - 조회성 intent → cheap
  - 배송지 변경 → standard
  - 환불/보상 → strong
- `eval_day2.py`에 새로운 case를 하나 추가하고 ASR/FPR/Utility가 어떻게 바뀌는지 확인합니다.

---

## 55–60분 · Mini challenge

하나를 골라서 graph와 eval을 같이 바꿉니다.

1. 다른 고객 주문 조회 scenario 추가
2. standard 고객 배송 지연 보상 scenario 추가
3. `exchange_request` intent 추가
4. human approval node 추가

결과 정리:

```text
추가한 case:
바꾼 파일:
막으려는 위험:
실행 명령:
평가 결과:
```

---

## Solutions 사용 순서

| 사용 시점 | 위치 | 용도 |
|---|---|---|
| baseline 실행 후 | `solutions/step01_baseline/` | 처음 graph 구조 비교 |
| guardrail 실습 뒤 | `solutions/step02_guardrails/` | 패턴/경계 조건 비교 |
| cost lab 뒤 | `solutions/step03_cost_routing/` | auto routing 정책 비교 |
| mini challenge 뒤 | `solutions/step04_eval_extended/` | 새 intent + eval case 참고 |
| 전체 실습 뒤 | `solutions/final/` | 전체 최종 참고본 |

Day 2는 `graph.py`, `guardrails.py`, `model_policy.py`, `eval_day2.py`가 함께 바뀌므로 Day 1처럼 단일 파일 snapshot이 아니라 패키지 폴더 snapshot으로 제공합니다.

---

## 예상 이슈

| 증상 | 조치 |
|---|---|
| `No module named langgraph.checkpoint.sqlite` | `pip install -r requirements.txt` 재실행 |
| live LLM 호출이 API key 오류로 실패 | `.env`의 `GEMINI_API_KEY` 확인. 구조 확인만 할 때는 `--llm-mode mock` 사용 |
| resume 했는데 pending node 없음 | 이미 끝난 thread. 새 `--thread-id` 사용 |
| checkpoint DB가 꼬인 느낌 | `rm day2_aicc/checkpoints/day2.sqlite*` 후 재실행 |
| eval pass가 갑자기 변함 | TODO 수정 후 기대값도 함께 업데이트 필요 |

---

## 마무리 정리

Agent 운영에서는 모델 성능만 보지 않습니다. 상태를 어디까지 저장할지, 어떤 context를 믿을지, 어떤 tool을 누가 승인할지, 어떤 요청을 어떤 모델에 보낼지까지 정해야 합니다. Day 2 실습 코드는 그 결정을 작게 압축한 샘플입니다.
