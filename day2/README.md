# Day 2 실습 — Cost 비교와 Security Guardrail

Day 2는 두 개 실습만 해요.

1. **Cost lab**: 같은 요약 과제를 여러 모델에 보내고 결과물, token, 비용, latency를 비교해요.
2. **Security lab**: PII, hallucination, topic drift, prompt injection 문제가 생기는 baseline을 먼저 보고, guard를 켰을 때 결과가 어떻게 바뀌는지 확인해요.

---

## 설치와 API key

```bash
cd kisa-ai-agent-practice
pip install -r requirements.txt
```

실제 Gemini 호출을 쓰려면 `.env`에 `GEMINI_API_KEY`를 넣어요. 네트워크/API 문제 없이 구조만 볼 때는 `--llm-mode mock`을 붙여요.

---

## Lab 1 · Cost 비교

```bash
python3 day2/cost_lab.py --llm-mode mock
```

실제 모델 호출:

```bash
python3 day2/cost_lab.py --models cheap,standard,strong
```

결과에서 볼 것:

| 항목 | 의미 |
|---|---|
| `profile` | cheap / standard / strong 비교용 이름 |
| `model` | 실제 호출 model id 또는 mock profile |
| `latency` | 응답까지 걸린 시간 |
| `input_tokens` | system prompt + input 원문 token |
| `output_tokens` | 모델이 만든 답변 token |
| `estimated_cost_usd` | token과 profile 가격표로 계산한 추정 비용 |
| `output` | 모델별 요약 품질 차이 |

수정해볼 곳:

- `prompts.py`의 `COST_SYSTEM_PROMPT`
- `prompts.py`의 `COST_INPUT_TEXT`
- `model_catalog.py`의 model id와 가격표

리포트:

```bash
cat day2/reports/cost_latest.md
```

---

## Lab 2 · Security Guardrail

문제가 생기는 baseline과 guard를 켠 결과를 같이 봐요.

```bash
python3 day2/security_lab.py --llm-mode mock --mode both
```

Guarded 결과만 확인:

```bash
python3 day2/security_lab.py --llm-mode mock --mode guarded
```

다루는 케이스:

| category | baseline에서 생기는 문제 | guarded에서 확인할 것 |
|---|---|---|
| PII | 전화번호/이메일 원문 노출 | 마스킹 |
| hallucination | 근거 없는 환불 확정 | 확인 필요 답변 |
| topic drift | 고객지원 밖 코딩 요청 응답 | 범위 밖 요청 거절 |
| prompt injection | 시스템 프롬프트 공개/보안 우회 | 공격 요청 차단 |

수정해볼 곳:

- `security_controls.py`의 `TODO-D2-SEC-01`: PII 패턴 추가
- `security_controls.py`의 `TODO-D2-SEC-02`: prompt injection 패턴 추가
- `prompts.py`의 `SECURITY_SYSTEM_PROMPT_GUARDED`: 근거 기반 답변 규칙 수정

리포트:

```bash
cat day2/reports/security_latest.md
```

---

## 60분 진행안

| 시간 | 파트 | 할 일 |
|---:|---|---|
| 0–5분 | 구조 확인 | Day 2가 cost/security 두 실습으로 나뉜다는 점 확인 |
| 5–25분 | Cost lab | 같은 input을 cheap/standard/strong으로 돌리고 품질·token·비용·latency 비교 |
| 25–35분 | Cost TODO | system prompt나 input을 바꿔 output/cost 변화 확인 |
| 35–50분 | Security lab | baseline 실패와 guarded 결과 비교 |
| 50–57분 | Security TODO | PII/prompt injection 패턴 하나씩 추가하고 재실행 |
| 57–60분 | 정리 | 어떤 모델을 어디에 쓸지, guard를 어느 layer에 둘지 정리 |

---

## 파일 구조

```text
day2/
├── cost_lab.py              # Lab 1 실행
├── security_lab.py          # Lab 2 실행
├── prompts.py               # system prompt와 input 원문
├── model_catalog.py         # model id, token 가격표
├── llm_client.py            # Gemini/mock 호출
├── security_cases.py        # 보안 케이스 4개
├── security_controls.py     # PII, injection, topic guard
├── report_writer.py         # markdown/json 리포트 저장
├── reports/                 # 실행 결과
└── solutions/               # reference runner
```
