# KISA AI Agent Practice

강의 실습 repo를 Day 1 / Day 2 구조로 나눠뒀어요.

| 구분 | 위치 | 주제 | 실행 시작점 |
|---|---|---|---|
| Day 1 | `day1/` | 단일 ReAct Agent, tool loop, Langfuse trace, golden set 평가 | `cd day1 && python3 check_env.py` |
| Day 2 | `day2/` | 모델 비용 비교, security guardrail | `python3 day2/cost_lab.py --llm-mode mock` |

기존 Day 1 자료는 `day1/`에 있어요. Day 2는 cost와 security 두 실습만 다뤄요.

---

## 설치

```bash
python3 -m venv .venv
source .venv/bin/activate    # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Codespaces/devcontainer를 쓰면 `requirements.txt` 설치가 자동으로 실행돼요.

---

## Day 1 빠른 시작

```bash
cd day1
cp .env.example .env
python3 check_env.py
python3 agent.py "production logs 상태 요약해줘"
python3 evaluate.py
```

Day 1 guide:

```bash
open day1/INSTRUCTOR_GUIDE.md
```

---

## Day 2 빠른 시작

```bash
python3 day2/cost_lab.py --llm-mode mock
python3 day2/security_lab.py --llm-mode mock --mode both
```

Live Gemini 호출을 쓰려면 `.env`에 `GEMINI_API_KEY`를 넣고 `--llm-mode mock`을 빼요.

Day 2 guide:

```bash
open day2/INSTRUCTOR_GUIDE.md
```

---

## Repo 구조

```text
.
├── day1/                 # Day 1 실습
├── day2/                 # Day 2 cost/security 실습
├── requirements.txt      # 공통 dependency
├── README.md             # 전체 안내
└── INSTRUCTOR_GUIDE.md   # 전체 진행 허브
```
