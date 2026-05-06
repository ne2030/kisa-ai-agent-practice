# KISA AI Agent Practice

강의 실습 repo를 Day 1 / Day 2 구조로 나눴습니다.

| 구분 | 위치 | 주제 | 실행 시작점 |
|---|---|---|---|
| Day 1 | `day1/` | 단일 ReAct Agent, tool loop, Langfuse trace, golden set 평가 | `cd day1 && python3 check_env.py` |
| Day 2 | `day2_aicc/` | AICC/e-commerce Agent, LangGraph, checkpoint, guardrails, cost 비교 | `python -m day2_aicc.app --scenario order_status` |

기존 Day 1 자료는 `day1/`로 옮겨 두었습니다. 루트에는 전체 과정 안내와 공통 dependency만 남깁니다.
Day 2 checkpoint는 `day2_aicc/solutions/`에 있습니다.

---

## 설치

```bash
python3 -m venv .venv
source .venv/bin/activate    # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Codespaces/devcontainer를 쓰면 `requirements.txt` 설치가 자동으로 실행됩니다.

---

## Day 1 빠른 시작

```bash
cd day1
cp .env.example .env
python3 check_env.py
python3 agent.py "production logs 상태 요약해줘"
python3 evaluate.py
```

Day 1 instructor guide:

```bash
open day1/INSTRUCTOR_GUIDE.md
```

> 루트의 `.env`를 이미 만들었다면 `cp ../.env .env`로 Day 1 폴더에 복사해도 됩니다.

---

## Day 2 빠른 시작

Day 2는 기본값으로 실제 Gemini LLM을 호출합니다. `GEMINI_API_KEY`가 필요하고, 오프라인 구조 검증이 필요할 때만 `--llm-mode mock`을 씁니다.

```bash
python -m day2_aicc.app --scenario order_status
python -m day2_aicc.app --scenario address_change_processing
python -m day2_aicc.app --scenario direct_injection
python -m day2_aicc.eval_day2 --compare-models
```

Day 2 instructor guide:

```bash
open day2_aicc/INSTRUCTOR_GUIDE.md
```

---

## Day 2 핵심 실험

### Checkpoint / resume

```bash
python -m day2_aicc.app \
  --scenario refund_recent \
  --thread-id demo-refund-1 \
  --interrupt-after retrieve_policy

python -m day2_aicc.app \
  --resume \
  --thread-id demo-refund-1
```

### Guardrail 비교

```bash
python -m day2_aicc.app --scenario indirect_policy --policy cheap --guards off
python -m day2_aicc.app --scenario indirect_policy --policy cheap --guards context,action
```

### Cost / model policy 비교

```bash
python -m day2_aicc.eval_day2 --compare-models
cat .eval/day2_eval_latest.md
```

---

## Repo 구조

```text
.
├── day1/                 # 기존 Day 1 실습
├── day2_aicc/            # Day 2 LangGraph AICC 실습
├── requirements.txt      # Day 1 + Day 2 공통 dependency
├── README.md             # 전체 안내
└── INSTRUCTOR_GUIDE.md   # 전체 진행 허브
```
