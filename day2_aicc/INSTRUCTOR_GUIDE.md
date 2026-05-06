# Day 2 Instructor Guide — AICC/e-commerce Agent

## 핵심 메시지

Day 1의 핵심은 “LLM 호출과 tool 호출이 loop로 묶인다”였습니다. Day 2의 핵심은 “운영 가능한 Agent는 graph, state, guardrail, cost policy, eval이 같이 필요하다”입니다.

수강생에게 강조할 흐름:

1. Agent가 고객응대 업무를 맡으면 읽기 tool과 쓰기 tool의 위험도가 달라짐
2. prompt injection은 사용자 입력뿐 아니라 외부 context에서도 들어옴
3. model을 바꾸면 비용만 변하는 게 아니라 실패 양상도 바뀜
4. checkpoint는 UX와 장애 복구에는 좋지만 state 설계가 나쁘면 민감정보·비용 문제가 생김

---

## 준비

```bash
cd kisa-ai-agent-practice
pip install -r requirements.txt
python -m day2_aicc.app --scenario order_status
```

정상 출력에 `final_answer`, `risk events`, `cost estimate`가 보이면 진행 가능합니다.

정답/checkpoint는 Day 1과 같은 용도로 `day2_aicc/solutions/`에 있습니다.

```bash
python -m day2_aicc.solutions.final.eval_day2 --compare-models
```

---

## 진행 스크립트

### 0–5분 · Day 1 연결

멘트:

> Day 1에서는 agent.py 안에서 ReAct loop를 직접 봤습니다. Day 2에서는 같은 아이디어를 고객응대 서비스처럼 나눕니다. 이제 중요한 질문은 “답변을 만들 수 있는가”가 아니라 “어떤 상태를 저장하고, 어떤 action을 막고, 어떤 모델을 어디에 쓸 것인가”입니다.

실행:

```bash
python -m day2_aicc.app --scenario order_status
```

짚을 부분:

- `risk_events`가 mini trace 역할
- `cost estimate`는 live billing이 아니라 비교용 local estimate
- `executed_actions`가 없으면 읽기 응답만 수행

### 5–12분 · 정상 업무 3종

```bash
python -m day2_aicc.app --scenario delivery_status
python -m day2_aicc.app --scenario address_change_processing
python -m day2_aicc.app --scenario compensation_delay
```

질문:

- 어떤 요청은 답변만 만들고, 어떤 요청은 tool action까지 가는가?
- 배송지 변경과 쿠폰 발급은 왜 더 위험한가?

### 12–20분 · Checkpoint

```bash
python -m day2_aicc.app --scenario refund_recent --thread-id demo-refund --interrupt-after retrieve_policy
python -m day2_aicc.app --resume --thread-id demo-refund
```

화이트보드:

```text
thread_id + checkpoint_id + next node
```

짚을 부분:

- LangGraph checkpoint는 thread 단위 state history
- 상담 중 브라우저가 닫히거나 worker가 죽어도 이어갈 수 있음
- state에 원문 개인정보나 거대한 context를 무제한 저장하면 위험

### 20–32분 · Tool boundary

실행:

```bash
python -m day2_aicc.app --scenario address_change_shipped --policy cheap --guards on
python -m day2_aicc.app --scenario address_change_shipped --policy cheap --guards off
python -m day2_aicc.app --scenario refund_old --policy cheap --guards on
python -m day2_aicc.app --scenario refund_old --policy cheap --guards off
```

설명 포인트:

- cheap profile은 shipped 주문에도 action을 제안할 수 있게 설계됨
- action_guard는 tool 실행 직전의 마지막 방어선
- 좋은 설계는 “모델이 틀려도 시스템이 안전”한 구조

학생 TODO:

- `TODO-D2-04`, `TODO-D2-09` 수정
- `guards=off`에서도 더 안전해지는지 확인

### 32–44분 · Prompt injection

Direct:

```bash
python -m day2_aicc.app --scenario direct_injection --guards on
python -m day2_aicc.app --scenario direct_injection --guards off
```

Indirect:

```bash
python -m day2_aicc.app --scenario indirect_policy --policy cheap --guards off
python -m day2_aicc.app --scenario indirect_policy --policy cheap --guards context,action
```

공격 성공 흐름:

```text
외부 FAQ/CMS 문서
  -> retrieve_policy
  -> 모델이 문서 속 instruction을 정책으로 착각
  -> issue_coupon 같은 쓰기 tool 제안
  -> action_guard 없으면 실제 실행
```

피해 예시:

- 쿠폰/환불 오발급
- 고객 개인정보 노출
- 내부 prompt/tool schema 노출
- CS ticket 조작과 운영 로그 오염

학생 TODO:

- `TODO-D2-07`, `TODO-D2-08` 패턴 추가
- context_guard만 켠 경우와 context+action을 같이 켠 경우 비교

### 44–54분 · Cost / model policy

```bash
python -m day2_aicc.eval_day2 --compare-models
cat .eval/day2_eval_latest.md
```

설명 포인트:

- 같은 scenario라도 cheap/standard/strong의 pass/quality/cost가 다름
- prompt caching 후보: system prompt, tool schema, policy instruction prefix
- batch 후보: golden set 평가, 야간 regression, offline judge
- 실시간 고객응대에는 batch가 맞지 않음

학생 TODO:

- `TODO-D2-06` auto routing 수정
- 조회성 intent는 cheap, 금전성 action은 standard/strong으로 라우팅
- strict budget에서 policy doc 수를 줄였을 때 품질 저하 확인

### 54–60분 · Mini challenge

선택지:

1. 다른 고객 주문 조회 scenario 추가
2. standard 고객 배송 지연 보상 scenario 추가
3. `exchange_request` intent 추가
4. human approval node 추가

공유 형식:

```text
내가 추가한 case:
막으려는 위험:
실행 명령:
평가 결과:
```

---

## 시간 부족 시 축약판

필수 실행만:

```bash
python -m day2_aicc.app --scenario address_change_shipped --policy cheap --guards on
python -m day2_aicc.app --scenario indirect_policy --policy cheap --guards off
python -m day2_aicc.app --scenario indirect_policy --policy cheap --guards context,action
python -m day2_aicc.eval_day2 --compare-models
```

핵심 질문 3개:

1. 모델이 잘못 제안한 action을 어디서 막았나?
2. 외부 context payload는 input guard로 잡히나?
3. cheap model이 정말 싸기만 한 선택인가?

---

## Solutions 공개 순서

| 공개 시점 | 위치 | 용도 |
|---|---|---|
| baseline 실행 후 | `solutions/step01_baseline/` | 처음 graph 구조 비교 |
| guardrail 실습 후 | `solutions/step02_guardrails/` | 패턴/경계 조건 정답 비교 |
| cost lab 후 | `solutions/step03_cost_routing/` | auto routing 정책 비교 |
| mini challenge 후 | `solutions/step04_eval_extended/` | 새 intent + eval case 참고 |
| 수업 종료 후 | `solutions/final/` | 전체 최종 참고본 |

Day 2는 `graph.py`, `guardrails.py`, `model_policy.py`, `eval_day2.py`가 함께 바뀌므로 Day 1처럼 단일 파일 snapshot이 아니라 패키지 폴더 snapshot으로 제공합니다.

---

## 예상 이슈

| 증상 | 조치 |
|---|---|
| `No module named langgraph.checkpoint.sqlite` | `pip install -r requirements.txt` 재실행 |
| resume 했는데 pending node 없음 | 이미 끝난 thread. 새 `--thread-id` 사용 |
| checkpoint DB가 꼬인 느낌 | `rm day2_aicc/checkpoints/day2.sqlite*` 후 재실행 |
| eval pass가 갑자기 변함 | TODO 수정 후 기대값도 함께 업데이트 필요 |

---

## 마무리 멘트

> Agent 운영에서 중요한 건 “모델이 똑똑하다” 하나가 아닙니다. 상태를 어디까지 저장할지, 어떤 context를 믿을지, 어떤 tool을 누가 승인할지, 어떤 요청을 어떤 모델에 보낼지까지 정해야 합니다. Day 2 실습 코드는 그 결정을 작게 압축한 샘플입니다.
