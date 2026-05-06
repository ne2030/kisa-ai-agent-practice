# Day 2 실습 — Cost 비교와 Security Guardrail

Day 2는 두 개 실습만 해요.

1. **Cost lab**: 모델, prompt, token, latency, 비용을 하나씩 바꿔가며 비교해요. Golden dataset으로 품질 평가도 같이 봐요.
2. **Security lab**: PII, hallucination, topic drift, prompt injection 문제가 생기는 baseline을 먼저 보고, guard를 켰을 때 결과가 어떻게 바뀌는지 확인해요.

---

## 설치와 API key

```bash
cd kisa-ai-agent-practice
pip install -r requirements.txt
```

실습 기본값은 실제 Gemini 호출이에요. `.env`에 `GEMINI_API_KEY`를 넣고 실행해요. 네트워크나 quota 문제로 진행이 막힐 때만 `--llm-mode mock`을 fallback으로 붙여요.

---

## Lab 1 · Cost 비교

한 번에 여러 모델을 자동으로 돌리지 않아요. 하나 실행하고, 결과를 보고, 다음 값을 바꿔서 다시 실행해요.

### 1) case 확인

```bash
python3 day2/cost_lab.py --list-cases
```

Golden dataset은 여기 있어요.

```bash
sed -n '1,180p' day2/cost_golden_set.yaml
```

### 2) cheap 모델 실행

```bash
python3 day2/cost_lab.py --profile cheap --prompt-style structured
python3 day2/cost_eval.py --report day2/reports/cost_latest.json
```

### 3) standard 모델로 바꿔서 실행

```bash
python3 day2/cost_lab.py --profile standard --prompt-style structured
python3 day2/cost_eval.py --report day2/reports/cost_latest.json
```

### 4) strong 모델로 바꿔서 실행

```bash
python3 day2/cost_lab.py --profile strong --prompt-style structured
python3 day2/cost_eval.py --report day2/reports/cost_latest.json
```

Live 호출도 같은 방식이에요.

```bash
python3 day2/cost_lab.py --profile standard --prompt-style structured
python3 day2/cost_eval.py --report day2/reports/cost_latest.json
```

결과에서 볼 것:

| 항목 | 의미 |
|---|---|
| `input` | system prompt + input 원문 token |
| `visible` | 화면에 보이는 답변 token |
| `think` | 화면에는 안 보이지만 비용에 들어가는 thinking token |
| `cached` | prompt caching hit가 난 input token |
| `total` | provider usage metadata 기준 total token |
| `est.cost` | token과 profile 가격표로 계산한 추정 비용 |
| `finish` | `STOP`, `MAX_TOKENS` 같은 종료 이유 |

### 5) prompt style 바꿔보기

```bash
python3 day2/cost_lab.py --profile standard --prompt-style concise
python3 day2/cost_eval.py --report day2/reports/cost_latest.json

python3 day2/cost_lab.py --profile standard --prompt-style detailed
python3 day2/cost_eval.py --report day2/reports/cost_latest.json

python3 day2/cost_lab.py --profile standard --prompt-style json
python3 day2/cost_eval.py --report day2/reports/cost_latest.json
```

볼 포인트:

- `concise`는 싸지만 누락이 생길 수 있어요.
- `detailed`는 품질은 좋아질 수 있지만 output token이 늘어요.
- `json`은 후처리가 쉬워지지만 구조 token이 추가돼요.

수정해볼 곳:

- `prompts.py`의 `COST_PROMPT_STYLES`
- `cost_golden_set.yaml`의 `required_terms`, `forbidden_terms`
- `model_catalog.py`의 model id와 가격표

---

## Lab 1-2 · 월간 비용, prompt caching, batch

마지막 실행 report의 token 수를 기준으로 월간 비용을 계산해요.

기본 월간 비용:

```bash
python3 day2/cost_projection.py --report day2/reports/cost_latest.json
```

Prompt caching hit가 70%라고 가정:

```bash
python3 day2/cost_projection.py --report day2/reports/cost_latest.json --cache-hit-rate 0.7
```

절반을 batch로 돌린다고 가정:

```bash
python3 day2/cost_projection.py --report day2/reports/cost_latest.json --batch-ratio 0.5
```

Caching + batch를 같이 적용:

```bash
python3 day2/cost_projection.py --report day2/reports/cost_latest.json --cache-hit-rate 0.7 --batch-ratio 0.5
```

볼 포인트:

- API 응답은 dollar 비용을 바로 주지 않고 token count를 줘요. 비용은 가격표와 곱해서 추정해요.
- prompt caching hit token은 `cached_content_token_count`로 확인해요.
- batch는 표준 interactive 비용보다 싸지만 비동기라 실시간 채팅에는 안 맞아요.
- 비용 최적화는 모델 downgrade만이 아니라 prompt 길이, output 길이, caching, batch를 같이 봐야 해요.

---

## Lab 2 · Security Guardrail

문제가 생기는 baseline과 guard를 켠 결과를 같이 봐요.

```bash
python3 day2/security_lab.py --mode both
```

Guarded 결과만 확인:

```bash
python3 day2/security_lab.py --mode guarded
```

다루는 케이스:

| category | baseline에서 생기는 문제 | guarded에서 확인할 것 |
|---|---|---|
| PII | 전화번호/이메일이 나옴 | `[PII_MASKED]`로 바뀜 |
| hallucination | 근거 없는 환불 확정 | 확인 필요로 바뀜 |
| topic drift | 고객지원 밖 코딩 요청 응답 | 범위 밖 요청 거절 |
| prompt injection | 시스템 프롬프트 공개/보안 우회 | 공격 요청 차단 |

수정해볼 곳:

- `security_controls.py`의 `TODO-D2-SEC-01`: PII 패턴 추가
- `security_controls.py`의 `TODO-D2-SEC-02`: prompt injection 패턴 추가
- `prompts.py`의 `SECURITY_SYSTEM_PROMPT_GUARDED`: 근거 기반 답변 규칙 수정

---

## 60분 진행안

| 시간 | 파트 | 할 일 |
|---:|---|---|
| 0–5분 | 구조 확인 | cost/security 두 실습과 실행 파일 확인 |
| 5–15분 | Cost model | cheap → eval, standard → eval, strong → eval 순서로 직접 실행 |
| 15–25분 | Cost prompt | `concise`, `detailed`, `json` 중 하나씩 바꿔 실행 |
| 25–35분 | Cost projection | 월간 비용, caching, batch 비율 바꿔 보기 |
| 35–50분 | Security lab | baseline 실패와 guarded 결과 비교 |
| 50–57분 | Security TODO | PII/prompt injection 패턴 하나씩 추가하고 재실행 |
| 57–60분 | 정리 | 어떤 모델을 어디에 쓰고, 어떤 guard를 둘지 정리 |

---

## 파일 구조

```text
day2/
├── cost_lab.py              # Lab 1 실행. 모델/prompt/case 하나씩 실행
├── cost_eval.py             # Golden dataset 기반 품질 평가
├── cost_projection.py       # 월간 비용, prompt caching, batch 계산
├── cost_golden_set.yaml     # Cost 평가용 golden dataset
├── cost_dataset.py          # Golden dataset loader
├── security_lab.py          # Lab 2 실행
├── prompts.py               # prompt style과 security prompt
├── model_catalog.py         # model id, token 가격표, caching/batch 가격
├── llm_client.py            # Gemini/mock 호출, usage metadata 정리
├── security_cases.py        # 보안 케이스 4개
├── security_controls.py     # PII, injection, topic guard
├── report_writer.py         # markdown/json 리포트 저장
├── reports/                 # 실행 결과
└── solutions/               # reference runner
```
