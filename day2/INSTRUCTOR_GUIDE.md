# Day 2 Guide — Cost Evaluation과 Security Guardrails

Day 2 실습 목표는 두 가지예요.

1. 같은 입력을 여러 모델과 prompt style로 돌려 보고, 품질·token·비용·latency 차이를 숫자로 확인
2. 보안 문제가 생기는 baseline을 보고, 간단한 guard를 적용하면 결과가 어떻게 바뀌는지 확인

---

## 전체 흐름

```text
Cost lab
  cost_golden_set.yaml
  -> cost_lab.py
  -> llm_client.py
  -> reports/cost_latest.md
  -> cost_eval.py
  -> reports/cost_eval_latest.md
  -> cost_projection.py
  -> reports/cost_projection_latest.md

Security lab
  security_cases.py
  -> security_lab.py baseline
  -> security_controls.py guarded
  -> reports/security_latest.md
```

---

## 준비

```bash
pip install -r requirements.txt
```

Live 호출이 기본이에요. `.env`의 `GEMINI_API_KEY`가 필요해요. 수업 중 네트워크나 quota가 막힐 때만 `--llm-mode mock`을 fallback으로 써요.

---

## 0–5분 · Day 2 구조 확인

```bash
find day2 -maxdepth 2 -type f | sort
sed -n '1,160p' day2/README.md
```

확인할 것:

- Day 2는 cost evaluation과 security guardrail 두 축으로 진행
- Cost는 `cost_lab.py`, `cost_eval.py`, `cost_repeat.py`, `cost_projection.py` 순서로 봄
- Golden dataset은 `cost_golden_set.yaml`에 있음
- 보안 케이스와 guard는 `security_cases.py`, `security_controls.py`에 있음

---

## 5–15분 · Naive prompt와 structured prompt 비교

먼저 cost 실습에서 쓰는 입력과 프롬프트를 읽고 시작해요. 이 구간은 `cheap` profile로 시작해요. cheap도 결론을 꽤 잘 맞힐 수 있다는 걸 먼저 보고, 그 다음 eval로 운영 기준에서 무엇이 빠졌는지 확인해요. 여기서 보려는 건 cheap 실패가 아니라, 싼 모델과 짧은 prompt가 어디까지 충분하고 어디서 보강이 필요한지예요.

### 입력 데이터가 뭔지

기본 case는 `latest-status-wins`예요. 고객지원에서 자주 나오는 배송지 변경 문의예요.

```text
고객 문의
- ORD-4219 배송지를 바꾸고 싶음
- 오전에 상담사에게 아직 출고 전이라고 들었다고 말함

상담 메모와 물류 이벤트
- 09:10 이전 상담 메모: 화면에는 출고 준비 중으로 보였음
- 09:25 물류 이벤트: LABEL_CREATED
- 09:43 물류 이벤트: PICKED_UP
- 09:50 최신 물류 상태: IN_TRANSIT

운영 정책
- 송장 생성 전에는 배송지 변경 가능
- LABEL_CREATED 이후에는 배송지 변경 불가
- PICKED_UP 이후에는 출고 보류도 불가
- 상담 메모와 물류 이벤트가 충돌하면 가장 늦은 시각의 물류 이벤트 우선
```

사람이 보면 어렵지 않아요. 오전 메모보다 09:50 상태가 더 최신이고, 현재 `IN_TRANSIT`이라 배송지 변경은 불가예요. 그런데 모델은 짧게 요약하라는 요청을 받으면 결론만 말하고 `LABEL_CREATED`, `PICKED_UP`, `IN_TRANSIT`, `최신 상태 우선` 같은 평가 기준을 빠뜨릴 수 있어요.

원본 데이터는 여기서 봐요.

```bash
sed -n '1,70p' day2/cost_golden_set.yaml
```

### naive prompt가 뭔지

`naive`는 일부러 거의 아무 기준도 주지 않은 요청이에요.

```text
아래 내용을 요약해줘.
```

이 프롬프트로도 모델이 결론을 맞힐 수는 있어요. 다만 운영자가 실제로 필요한 상태값, 시간 순서, 가능/불가 근거, 확인 필요 항목이 빠질 수 있어요.

### structured prompt가 뭔지

`structured`는 역할, 출력 형식, 보존해야 할 정보, 충돌 처리 기준을 같이 줘요.

```text
너는 고객지원 운영 리더를 돕는 분석가야.
아래 원문을 읽고 한국어로 간결하게 요약해.
출력 형식:
1. 핵심 요약 3줄
2. 고객 영향
3. 원인 후보
4. 바로 할 다음 조치
5. 확실하지 않은 내용
근거에 없는 내용은 확정하지 마.
중요한 코드, 주문번호, 시간, 기간, 금액, 정책 예외, 불가 조건은 원문 표현을 최대한 그대로 남겨.
서로 충돌하는 정책이나 메모가 있으면 우선순위와 확인 필요 항목을 분리해.
일반 메모와 최신 상태가 충돌하면 최신 상태를 우선해.
상태값은 번역만 하지 말고 원문 코드를 같이 남겨.
주문 취소, 배송지 변경, 출고 보류처럼 서로 다른 처리 항목은 각각 가능/불가를 분리해.
```

프롬프트 원문은 여기서 봐요.

```bash
sed -n '1,90p' day2/prompts.py
```

### 이 비교를 하는 이유

요약 품질은 한 문장으로 “좋다/별로다”라고 판단하기 어려워요. 그래서 이 실습에서는 golden dataset에 기준을 넣어두고, 모델 출력이 그 기준을 얼마나 만족하는지 점수로 봐요.

`latest-status-wins`에서 기준은 이런 식이에요.

- 있어야 하는 말: `ORD-4219`, `LABEL_CREATED`, `PICKED_UP`, `IN_TRANSIT`, `배송지 변경`, `불가`, `최신`
- 나오면 안 되는 말: `배송지 변경 가능합니다`, `출고 보류 가능합니다`, `출고 전 상태입니다`
- 루브릭: 정확성, 근거성, 활용성

여기서 봐야 할 포인트는 세 가지예요.

1. `cheap + naive`도 결론 자체는 맞힐 수 있어요. 이게 실제 비용 설계에서 중요한 출발점이에요.
2. `naive`는 input token이 적고 비용도 낮지만, 필요한 기준어와 구조가 빠질 수 있어요.
3. `structured`는 input token이 늘어 비용이 조금 올라가지만, 답변 형식과 판단 기준을 더 안정적으로 고정해요.
4. 비용 비교는 모델 가격만 보는 게 아니라 prompt 길이, output 길이, latency, eval 점수를 같이 봐야 해요.

### 실행

같은 profile에서 prompt style만 바꿔 실행하고 eval 결과를 확인해요.

```bash
python3 day2/cost_lab.py --case latest-status-wins --profile cheap --prompt-style naive
python3 day2/cost_eval.py --report day2/reports/cost_latest.json

python3 day2/cost_lab.py --case latest-status-wins --profile cheap --prompt-style structured
python3 day2/cost_eval.py --report day2/reports/cost_latest.json
```

### 결과에서 볼 것

`cost_lab.py` 결과에서는 token과 비용을 봐요.

- `input`: 프롬프트와 입력 원문 token
- `visible`: 화면에 보이는 답변 token
- `think`: 화면에는 안 보이지만 비용에 들어가는 thinking token
- `total`: provider usage metadata 기준 total token
- `est.cost`: 가격표를 곱해서 계산한 추정 비용
- `latency`: 응답까지 걸린 시간

`cost_eval.py` 결과에서는 품질을 봐요.

- 정확성: 필요한 주문번호, 상태값, 결론이 들어갔는지
- 근거성: 원문과 반대되는 확정 표현이 없는지
- 활용성: 운영자가 바로 쓸 수 있게 결론, 근거, 다음 조치, 확인 필요 항목이 나뉘었는지
- missing terms: 답변에서 빠진 기준어가 무엇인지

예상되는 차이는 이런 모양이에요.

```text
cheap + naive
- 결론은 맞힐 수 있음
- 비용과 latency가 낮게 나올 수 있음
- 최신 상태나 상태값 일부, 확인 항목, 구조가 빠질 수 있음
- 사람이 보기엔 괜찮아도 eval에서는 missing terms가 나올 수 있음

cheap + structured
- 답변이 길어지고 비용은 올라갈 수 있음
- 상태값과 판단 기준이 더 잘 남음
- eval 점수가 안정적으로 나올 가능성이 높음
```

보고서 파일도 같이 열어봐요.

```bash
sed -n '1,220p' day2/reports/cost_latest.md
sed -n '1,260p' day2/reports/cost_eval_latest.md
```

---

## 15–23분 · Cost model 직접 비교

앞에서 `cheap + structured`를 봤으니, 같은 structured prompt를 `standard`, `strong`으로 바꿔 실행해요. 세 결과를 나란히 놓고 품질이 충분히 좋아지는지, 비용과 latency가 얼마나 늘어나는지 확인해요.

```bash
python3 day2/cost_lab.py --case latest-status-wins --profile standard --prompt-style structured
python3 day2/cost_eval.py --report day2/reports/cost_latest.json

python3 day2/cost_lab.py --case latest-status-wins --profile strong --prompt-style structured
python3 day2/cost_eval.py --report day2/reports/cost_latest.json
```

코드 위치:

```bash
sed -n '1,220p' day2/cost_lab.py
sed -n '1,120p' day2/prompts.py
sed -n '1,180p' day2/cost_golden_set.yaml
sed -n '1,220p' day2/cost_eval.py
sed -n '1,160p' day2/model_catalog.py
```

볼 것:

- cheap이 결론을 잘 맞히면 그 자체가 중요한 결과임
- standard나 strong으로 바꿨을 때 eval 점수가 크게 좋아지지 않으면 cheap을 쓰는 판단도 가능함
- eval은 "느낌상 좋아 보임"이 아니라 required/forbidden 기준으로 점수화함
- 모델이 좋아 보여도 token과 latency가 같이 올라갈 수 있음
- `visible`과 `think`를 나눠서 봐야 함

Live 호출에서 flash/pro 출력이 짧거나 비어 보이면 이 순서로 확인해요.

1. `finish`가 `MAX_TOKENS`인지 확인
2. `think`가 큰데 `visible`이 작은지 확인
3. `--max-output-tokens 4096`으로 다시 실행
4. `model_catalog.py`의 `default_thinking_budget` 확인

현재 코드는 Gemini 2.5 Flash 계열은 thinking budget을 0으로 두고, Pro는 128로 낮춰서 수업 중 visible output이 안 잘리게 해뒀어요.

---

## 23–30분 · 반복 실행으로 응답 흔들림 보기

앞에서 본 `cheap` 조건을 2회씩 반복 실행해요.

```bash
python3 day2/cost_repeat.py --case latest-status-wins --profile cheap --prompt-style naive --runs 2
python3 day2/cost_repeat.py --case latest-status-wins --profile cheap --prompt-style structured --runs 2
```

볼 것:

- score range
- visible output range
- missing terms
- 같은 profile에서도 prompt style에 따라 출력 흔들림이 달라지는지

---

## 30–35분 · 월간 비용, prompt caching, batch

마지막 cost report를 기준으로 월간 비용을 계산해요.

```bash
python3 day2/cost_projection.py --report day2/reports/cost_latest.json
python3 day2/cost_projection.py --report day2/reports/cost_latest.json --cache-hit-rate 0.7
python3 day2/cost_projection.py --report day2/reports/cost_latest.json --batch-ratio 0.5
python3 day2/cost_projection.py --report day2/reports/cost_latest.json --cache-hit-rate 0.7 --batch-ratio 0.5
```

볼 것:

- `daily_requests * business_days`가 월간 요청 수가 됨
- prompt caching은 반복되는 input prefix 비용을 줄이는 쪽
- batch는 비용을 낮출 수 있지만 비동기라 고객 채팅 응답에는 안 맞음
- 실시간 고객 응대와 백오피스 분석을 분리해야 비용 설계가 쉬워짐

API 응답에서 바로 볼 수 있는 값:

```text
prompt_token_count
candidates_token_count
thoughts_token_count
cached_content_token_count
total_token_count
```

바로 안 나오는 값:

```text
이 요청에 청구된 최종 dollar 금액
```

그래서 실습 코드는 usage metadata token 수와 `model_catalog.py` 가격표를 곱해서 비용을 추정해요. 실제 청구액은 provider billing 쪽에서 다시 확인해야 해요.

---

## 35–50분 · Security lab 실행

```bash
python3 day2/security_lab.py --mode both
```

볼 것:

| category | baseline | guarded |
|---|---|---|
| PII | 전화번호/이메일이 나옴 | `[PII_MASKED]`로 바뀜 |
| hallucination | 근거 없는 환불 확정 | 확인 필요로 바뀜 |
| topic drift | 코딩 요청에 답함 | 고객지원 범위 밖으로 거절 |
| prompt injection | 시스템 프롬프트 공개 | 우회 요청 차단 |

코드 위치:

```bash
sed -n '1,180p' day2/security_cases.py
sed -n '1,240p' day2/security_controls.py
sed -n '1,260p' day2/security_lab.py
```

---

## 50–57분 · Security 수정 실습

하나씩 바꿔요.

1. `security_controls.py`의 `실습-보안-01` 아래에 계정번호 regex 추가
2. `security_controls.py`의 `실습-보안-02` 아래에 한국어 우회 문구 추가
3. `prompts.py`의 guarded prompt에 “근거 문서에 없는 내용은 확정하지 말 것” 문구 강화

재실행:

```bash
python3 day2/security_lab.py --mode guarded --out-dir /tmp/day2-security-after
cat /tmp/day2-security-after/security_latest.md
```

---

## 57–60분 · 정리

마지막에는 아래 네 항목을 채워요.

```text
실시간 응답에 쓸 모델:
대량 비동기 작업에 쓸 모델:
prompt caching을 적용할 반복 context:
반드시 둘 guard:
```

---

## 자주 나는 문제

| 증상 | 조치 |
|---|---|
| `GEMINI_API_KEY is required` | `.env`에 유효한 key 넣기. 수업 진행이 막힐 때만 `--llm-mode mock` 사용 |
| live 결과가 매번 조금 다름 | 같은 case/profile/prompt를 2회 실행해 변동 폭 확인 |
| pro/flash 출력이 비거나 짧음 | `think`, `finish`, `--max-output-tokens` 확인 |
| eval이 실패함 | `cost_golden_set.yaml`의 missing/forbidden term 확인 |
| reports 파일이 안 보임 | `--out-dir` 경로 확인 |
