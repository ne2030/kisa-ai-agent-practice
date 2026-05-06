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
- Cost는 `cost_lab.py`, `cost_eval.py`, `cost_projection.py` 순서로 봄
- Golden dataset은 `cost_golden_set.yaml`에 있음
- 보안 케이스와 guard는 `security_cases.py`, `security_controls.py`에 있음

---

## 5–15분 · Cost model 직접 비교

여기서는 한 번에 여러 모델을 자동 비교하지 않아요. 하나 실행하고 eval을 보고, 그 다음 profile만 바꿔요.

```bash
python3 day2/cost_lab.py --profile cheap --prompt-style structured
python3 day2/cost_eval.py --report day2/reports/cost_latest.json

python3 day2/cost_lab.py --profile standard --prompt-style structured
python3 day2/cost_eval.py --report day2/reports/cost_latest.json

python3 day2/cost_lab.py --profile strong --prompt-style structured
python3 day2/cost_eval.py --report day2/reports/cost_latest.json
```

코드 위치:

```bash
sed -n '1,220p' day2/cost_lab.py
sed -n '1,180p' day2/cost_golden_set.yaml
sed -n '1,220p' day2/cost_eval.py
sed -n '1,160p' day2/model_catalog.py
```

볼 것:

- cheap이 항상 실패하는 건 아니고, 단순 요약에서는 꽤 잘할 수 있음
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

## 15–25분 · Prompt style 바꿔보기

같은 model에서 prompt를 바꿔요.

```bash
python3 day2/cost_lab.py --profile standard --prompt-style concise
python3 day2/cost_eval.py --report day2/reports/cost_latest.json

python3 day2/cost_lab.py --profile standard --prompt-style detailed
python3 day2/cost_eval.py --report day2/reports/cost_latest.json

python3 day2/cost_lab.py --profile standard --prompt-style json
python3 day2/cost_eval.py --report day2/reports/cost_latest.json
```

볼 것:

- prompt가 길어지면 input token이 늘어남
- 상세 답변을 요구하면 output token이 늘어남
- JSON은 후처리에는 좋지만 구조 token이 추가됨
- prompt 변경 뒤에는 비용뿐 아니라 eval score도 같이 봐야 함

간단 TODO:

1. `prompts.py`의 `COST_PROMPT_STYLES["concise"]`를 더 짧게 수정
2. 다시 실행
3. `cost_eval.py` 결과에서 빠진 required term 확인

---

## 25–35분 · 월간 비용, prompt caching, batch

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

## 50–57분 · Security TODO

하나씩 바꿔요.

1. `security_controls.py`의 `TODO-D2-SEC-01` 아래에 계정번호 regex 추가
2. `security_controls.py`의 `TODO-D2-SEC-02` 아래에 한국어 우회 문구 추가
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
