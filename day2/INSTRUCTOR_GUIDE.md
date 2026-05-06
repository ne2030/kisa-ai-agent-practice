# Day 2 Guide — Cost와 Security만 보기

Day 2 실습 목표는 두 가지예요.

1. 같은 입력을 여러 모델에 보내면 품질, token, 비용, latency가 어떻게 달라지는지 보기
2. 보안 문제가 생기는 baseline을 보고, 간단한 guard를 적용하면 결과가 어떻게 바뀌는지 보기

---

## 전체 흐름

```text
Cost lab
  prompts.py
  -> cost_lab.py
  -> llm_client.py
  -> model_catalog.py
  -> reports/cost_latest.md

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

Live 호출은 `.env`의 `GEMINI_API_KEY`가 필요해요. 수업 중 네트워크나 quota가 불안하면 `--llm-mode mock`으로 진행해요.

---

## 0–5분 · Day 2 구조 확인

```bash
find day2 -maxdepth 2 -type f | sort
sed -n '1,140p' day2/README.md
```

확인할 것:

- Day 2는 `cost_lab.py`와 `security_lab.py` 두 개만 실행
- prompt와 입력은 `prompts.py`에 있음
- 보안 케이스와 guard는 `security_cases.py`, `security_controls.py`에 있음

---

## 5–25분 · Cost lab 실행

```bash
python3 day2/cost_lab.py --llm-mode mock
```

Live 호출:

```bash
python3 day2/cost_lab.py --models cheap,standard,strong
```

볼 것:

- cheap은 빠르고 싸지만 요약이 짧거나 누락될 수 있음
- strong은 비싸고 느리지만 원인/리스크/다음 조치를 더 분리할 수 있음
- input token은 동일해도 output token이 늘면 비용이 커짐
- latency는 모델 크기와 네트워크 상태를 같이 봐야 함

코드 위치:

```bash
sed -n '1,120p' day2/prompts.py
sed -n '1,120p' day2/model_catalog.py
sed -n '1,180p' day2/cost_lab.py
```

---

## 25–35분 · Cost TODO

하나만 바꿔요.

1. `prompts.py`의 `COST_SYSTEM_PROMPT`에 “표로 요약해” 추가
2. `COST_INPUT_TEXT`를 더 길게 만들기
3. `model_catalog.py`에서 cheap/standard/strong 가격을 조정

재실행:

```bash
python3 day2/cost_lab.py --llm-mode mock --out-dir /tmp/day2-cost-after
cat /tmp/day2-cost-after/cost_latest.md
```

정리 질문:

- 비용 차이가 token 때문인지, model price 때문인지 구분되는가?
- output이 더 좋아졌는지, 그냥 길어진 것인지 어떻게 판단할까?

---

## 35–50분 · Security lab 실행

```bash
python3 day2/security_lab.py --llm-mode mock --mode both
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
sed -n '1,220p' day2/security_controls.py
sed -n '1,240p' day2/security_lab.py
```

---

## 50–57분 · Security TODO

하나씩 바꿔요.

1. `security_controls.py`의 `TODO-D2-SEC-01` 아래에 계정번호 regex 추가
2. `security_controls.py`의 `TODO-D2-SEC-02` 아래에 한국어 우회 문구 추가
3. `prompts.py`의 guarded prompt에 “근거 문서에 없는 내용은 확정하지 말 것” 문구 강화

재실행:

```bash
python3 day2/security_lab.py --llm-mode mock --mode guarded --out-dir /tmp/day2-security-after
cat /tmp/day2-security-after/security_latest.md
```

---

## 57–60분 · 정리

마지막에는 이 세 가지만 정리해요.

```text
내가 고른 모델:
그 이유:
반드시 둘 guard:
```

---

## 자주 나는 문제

| 증상 | 조치 |
|---|---|
| `GEMINI_API_KEY is required` | `.env` 확인 또는 `--llm-mode mock` 사용 |
| live 결과가 매번 조금 다름 | mock으로 비교 흐름 먼저 확인 |
| reports 파일이 안 보임 | `--out-dir` 경로 확인 |
