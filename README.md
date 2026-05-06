# Day 1 실습 — 단일 에이전트 만들고 검증하기

KISA AI Agent 강의 Day 1 핸즈온. **90분** 안에 ReAct 에이전트를 동작시키고, observability를 붙이고, 실패 케이스를 진단하고, golden dataset으로 평가하는 한 사이클을 완수합니다.

---

## 무엇을 만드나

- **agent.py** — Gemini 2.5 Flash 기반 ReAct loop. tool 호출을 직접 검증/실행
- **trace** — Langfuse `@observe` 데코레이터로 자동 trace 기록
- **failures/** — 의도적으로 망가진 시나리오 4종, trace로 진단 연습
- **evaluate.py** — `golden_set.yaml`의 5개 hard sample을 자동 평가

---

## 사전 준비

### A) GitHub Codespaces (권장 · 로컬 설치 불필요)

필요한 것: **GitHub 계정 + 브라우저 + 인터넷**. 그게 다.

1. 이 repo에서 우상단 **Code → Codespaces → Create codespace on main** 클릭
2. 컨테이너 부팅 (보통 1~5분). 브라우저 안에서 VS Code가 열림
3. `pip install`은 컨테이너 빌드 시점에 자동 완료. Python·git 등 모든 환경이 사전 설치됨

### B) 로컬 (백업 — Codespaces 못 쓰는 경우만)

#### 1) 사전 도구 확인

```bash
python3 --version   # Python 3.10 이상이 나와야 함
git --version       # git 설치 여부 확인
```

설치 안 되어 있다면:

| OS | Python | git |
|----|--------|-----|
| macOS | `brew install python@3.11` | `xcode-select --install` 또는 `brew install git` |
| Windows | [python.org/downloads](https://www.python.org/downloads/) — *Add Python to PATH* 체크 필수 | [git-scm.com/download/win](https://git-scm.com/download/win) |
| Linux | `sudo apt install python3.11 python3.11-venv` | `sudo apt install git` |

#### 2) repo clone + 가상환경 + 의존성

```bash
git clone https://github.com/ne2030/kisa-ai-agent-practice.git
cd kisa-ai-agent-practice
python3 -m venv .venv
source .venv/bin/activate    # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### `.env` 만들기

`.env.example`을 복사해서 `.env`로 저장한 뒤, 4개 값을 채워 넣습니다.

```bash
cp .env.example .env
```

| 키 | 어디서 |
|-----|--------|
| `GEMINI_API_KEY` | 강의자가 화면에 띄운 값을 복사 |
| `LANGFUSE_PUBLIC_KEY` | [cloud.langfuse.com](https://cloud.langfuse.com) 가입 → 프로젝트 생성 → Settings → API Keys |
| `LANGFUSE_SECRET_KEY` | 위와 동일 위치 |
| `LANGFUSE_HOST` | 기본값 `https://cloud.langfuse.com` 그대로 |

---

## Step 1 · 셋업 + Walkthrough (30분)

### 1-1. 환경 검증

```bash
python check_env.py
```

`✅ Gemini OK` + `✅ Langfuse OK` 두 줄 나오면 통과. 실패하면 `.env` 값을 다시 확인.

### 1-2. 코드 walkthrough (강의자 주도)

`agent.py`를 같이 읽으며 다음을 확인:

- `TOOLS` — schema 정의 (LLM에게 알려주는 인터페이스)
- `HANDLERS` — 실제 함수 매핑 (host application이 실행)
- `react_loop` — observe → decide → act → observe 반복
- 종료 조건 — function_call이 더 없으면 최종 답변 반환

### 1-3. baseline 실행

```bash
python agent.py
```

샘플 질문에 대해 터미널에서 모델이 `search_db`를 호출하는 흐름을 확인합니다.
Langfuse의 nested trace 확인은 Step 3에서 parent `@observe()`를 켠 뒤 진행합니다.

---

## Step 2 · 두 번째 Tool 추가 (10~15분)

`agent.py`의 **TODO 1** 자리에 `get_user_info(user_id: str)` mock tool을 추가합니다.

**기본:**
1. `search_db` 처럼 mock dict 기반 함수 정의
2. `TOOLS` 배열에 `FunctionDeclaration` 추가
3. `HANDLERS` dict에 함수 매핑 추가

테스트:
```bash
python agent.py
```
질문을 살짝 바꿔서 — 예: `"u001 사용자 정보와 production logs를 함께 알려줘"` — 두 tool이 모두 호출되는지 터미널 출력에서 확인.
Step 3 이후에는 같은 흐름을 Langfuse trace에서도 확인.

**옵션 (+):** 인자 validation
- `user_id`가 비어있거나 'u'로 시작하지 않으면 에러 반환
- LLM이 잘못된 인자를 넣었을 때 어떻게 반응하는지 trace로 관찰

---

## Step 3 · Langfuse @observe 데코레이터 (10~15분)

`agent.py`의 **TODO 2** 위치에 `@observe()` 데코레이터를 활성화합니다.
`llm.generate_content`와 `tool.execute` helper는 이미 span으로 계측되어 있으므로,
`react_loop`에 parent trace를 붙이면 Langfuse에서 nested 구조로 보입니다.

**기본:**
- `# @observe()` 주석을 풀어 한 줄을 활성화
- 다시 `python agent.py` 실행
- [cloud.langfuse.com](https://cloud.langfuse.com) 대시보드에서 본인 프로젝트의 **Tracing** 탭 열기
- 방금 실행한 trace를 클릭해서 nested span tree 확인

확인 포인트:
- `react_loop` 노드 (입력 / 출력 / 시간)
- 하위 `llm.generate_content` span — step, message count, tool call 요청
- 하위 `tool.execute` span — tool 이름, 인자, 반환값

**옵션 (+):** custom metadata
```python
from langfuse import get_client

get_client().update_current_span(
    metadata={
        "user_id": "your_nickname",
        "tags": ["day1"],
    },
)
```
이렇게 현재 span에 본인 식별자를 붙이면 다른 학생들과 구분됨.

---

## Step 4 · 의도적 실패 진단 (10~15분)

4개 시나리오를 차례로 돌려서 각자 trace로 진단합니다.

```bash
python failures/bad_tool_demo.py          # tool 이름 불일치
python failures/infinite_loop_demo.py     # 빈 결과 → 무한 재시도
python failures/hallucination_demo.py     # 빈 데이터에 그럴듯한 답
python failures/lazy_response_demo.py     # system prompt 부재 → "분석하겠습니다" punt
```

각 실행 후:
1. 터미널 메시지 읽기
2. Langfuse 대시보드에서 해당 trace 열기
3. **1줄 진단** — 어디서 어떻게 깨졌는지 본인 노트에 기록

**옵션 (+):** 1개 fix
- 4개 중 하나 골라 어떻게 수정해야 동작할지 가설 세우기
- 특히 `lazy_response_demo`는 한 줄 fix(`SYSTEM_INSTRUCTION` 채우기)가 모델 동작을 어떻게 바꾸는지 직접 비교 가능
- (실제로 코드를 고쳐 다시 돌려보면 더 좋음)

---

## Step 5 · Golden Dataset 평가 (10~15분)

5개의 hard sample을 자동 평가합니다.

```bash
python evaluate.py
```

각 case의 `passed` 여부 + 이유 출력. Langfuse trace에서도 evaluate 실행 흔적이 보임.

**기본:** `golden_set.yaml`에 본인 사례 1개 추가
```yaml
- id: my-001
  input: <본인이 만든 질문>
  expected:
    must_call_tools: ["search_db"]
    must_mention: ["..."]
    must_not_say: ["..."]
  notes: 어떤 약점/edge case를 잡으려는지 메모
```
재실행 → 추가한 case가 결과에 포함됐는지 확인.

**옵션 (+):** rubric 수정
- `evaluate.py`의 `check()` 함수를 더 엄격하게
- 예: 답변 길이 제한, 특정 패턴 부재 검증, 또는 LLM-as-Judge 추가
- 같은 case가 더 빡빡한 기준에서도 통과하는지 보기

---

## 트러블슈팅

### `ModuleNotFoundError: No module named '...'`
- Codespaces: 컨테이너가 아직 빌드 중일 수 있음. 잠시 대기
- 로컬: `pip install -r requirements.txt` 다시 실행, venv 활성화 확인

### `GEMINI_API_KEY` 미설정 에러
- `.env` 파일이 repo root, 즉 `kisa-ai-agent-practice/.env` 위치에 있는지
- key 양 옆에 따옴표/공백 없는지

### Langfuse 연결 실패
- public/secret 키가 같은 프로젝트에서 발급된 한 쌍인지
- `LANGFUSE_HOST`가 기본값 (`https://cloud.langfuse.com`) 인지

### Trace가 대시보드에 안 보임
- 1~2초 지연이 있을 수 있음, 새로고침
- 이 실습 스크립트들은 종료 시 `get_client().flush()`를 호출함
- 그래도 안 보이면 Langfuse key/host가 맞는지, `@observe()` 주석을 풀었는지 확인

---

## 막혔을 때

`solutions/agent.py` — TODO 1, 2가 채워진 정답. 직접 시도 후 비교용으로만 보세요.

---

## 끝나고

- 본인 Langfuse 대시보드는 *본인 소유*. 강의 끝나도 그대로 남음
- 집에서 코드를 더 다듬어 돌리면 trace가 누적됨
- `agent.py`를 본인 프로젝트의 시작점으로 활용해도 OK
