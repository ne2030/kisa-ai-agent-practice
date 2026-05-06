# Day 2 checkpoints

Day 1의 `solutions/`처럼 단계별 checkpoint를 제공합니다. Day 2는 한 파일이 아니라 graph/state/tool/guardrail/eval이 같이 움직이므로, 단계별 **패키지 폴더**로 구성합니다.

실행은 repo root에서 합니다. 기본값은 실제 Gemini LLM 호출이고, checkpoint 구조만 빠르게 확인할 때는 `--llm-mode mock`을 붙입니다.

```bash
python3 day2_aicc/solutions/step01_baseline/app.py --scenario order_status
python3 day2_aicc/solutions/final/eval_day2.py --compare-models --scenario refund_old
python3 day2_aicc/solutions/final/eval_day2.py --include-unguarded --policies cheap --llm-mode mock
```

---

## 진행 시나리오

| 단계 | 실행/비교 위치 | 코드 변화 | 확인 포인트 |
|---|---|---|---|
| Step 1 baseline | `solutions/step01_baseline/` | 기본 AICC graph, 3-layer guardrail, checkpoint, cost estimate | 정상 scenario와 injection scenario의 기본 흐름 |
| Step 2 guardrails | `solutions/step02_guardrails/` | 한국어 direct injection 패턴, HTML/base64 indirect 패턴, 배송지 변경 조건 강화 | input/context/action guard가 서로 다른 공격을 막는 위치 |
| Step 3 cost routing | `solutions/step03_cost_routing/` | `auto` routing: 조회 cheap, 주소변경 standard, 환불/보상 strong | 모델 변경에 따른 cost/quality 차이 |
| Step 4 eval 확장 | `solutions/step04_eval_extended/` | 교환 intent, 다른 고객 주문 차단 case, eval case 추가 | 새 업무를 graph/eval에 함께 추가하는 흐름 |
| Final | `solutions/final/` | Step 4와 같은 최종 참고본 | 전체 흐름 비교 |

---

## 자주 쓰는 비교 명령

### Baseline 동작

```bash
python3 day2_aicc/solutions/step01_baseline/app.py --scenario address_change_processing
python3 day2_aicc/solutions/step01_baseline/app.py --scenario indirect_policy --policy cheap --guards off
```

### Guardrail checkpoint 비교

```bash
python3 day2_aicc/solutions/step02_guardrails/app.py --scenario direct_injection
python3 day2_aicc/solutions/step02_guardrails/app.py --scenario indirect_policy --policy cheap --guards context,action
```

### Cost routing checkpoint 비교

```bash
python3 day2_aicc/solutions/step03_cost_routing/app.py --scenario order_status --policy auto --budget strict
python3 day2_aicc/solutions/step03_cost_routing/app.py --scenario compensation_delay --policy auto --budget strict
```

기대 흐름:

- `order_status` → cheap
- `compensation_delay` → strong

### Eval 확장 checkpoint 비교

```bash
python3 day2_aicc/solutions/step04_eval_extended/app.py --scenario exchange_recent
python3 day2_aicc/solutions/step04_eval_extended/app.py --scenario cross_customer_order
python3 day2_aicc/solutions/step04_eval_extended/eval_day2.py --compare-models --scenario exchange_recent
```

---

## 복사해서 적용하는 방법

한 단계 전체를 현재 실습 코드에 덮어쓸 때:

```bash
cp day2_aicc/solutions/step02_guardrails/guardrails.py day2_aicc/guardrails.py
cp day2_aicc/solutions/step03_cost_routing/model_policy.py day2_aicc/model_policy.py
```

Step 4는 여러 파일이 같이 바뀌므로 폴더를 비교하는 편이 안전합니다.

```bash
diff -ru day2_aicc day2_aicc/solutions/step04_eval_extended \
  --exclude solutions --exclude __pycache__ --exclude checkpoints
```

---

## 사용 팁

- 처음부터 `solutions/`를 보지 말고, 막히는 지점에서 해당 step만 비교합니다.
- Step 2는 guardrail 실습 뒤에 비교합니다.
- Step 3은 비용 section 뒤에 비교하면 `cheap/standard/strong` 토론이 자연스럽습니다.
- Step 4는 시간이 남을 때 확장 과제로 사용합니다.
