# Day 1 실습 진행 가이드

이 문서는 실습을 진행하면서 그대로 따라가기 위한 가이드입니다.
기본 작업 파일은 `agent.py`입니다. `solutions/`는 막혔을 때 비교하는 checkpoint입니다.

---

## 전체 목표

다음 흐름을 한 번 경험합니다.

1. Gemini 기반 ReAct loop 실행
2. 두 번째 tool 추가
3. Langfuse trace가 왜 처음에는 흩어져 보이는지 확인
4. parent `@langfuse.observe()`를 붙여 nested trace 만들기
5. 실패 케이스를 trace로 진단
6. golden dataset으로 자동 평가

핵심 메시지:

> Agent는 “LLM 한 번 호출”이 아니라 LLM 호출, tool 호출, loop, stop condition, observability가 묶인 application flow입니다.

---

## 빠른 진행 순서

| 순서 | 파트 | 목표 |
|---:|---|---|
| 1 | repo / env 준비 | `.env`, Gemini, Langfuse 연결 확인 |
| 2 | Step 1 baseline | `agent.py` 구조와 ReAct loop 이해 |
| 3 | Step 2 tool 추가 | `get_user_info` tool 추가 |
| 4 | Step 3 nested trace | parent observe 전/후 차이 확인 |
| 5 | Step 4 failure diagnosis | 실패 4종을 trace로 진단 |
| 6 | Step 5 evaluation | golden dataset 평가 |

시간이 적으면 1~4를 중심으로 진행하고, 5~6은 실행만 보여주거나 과제로 넘겨도 됩니다.

---

## 0. 시작 전

오늘 할 일:

> 완성된 agent framework를 쓰는 게 아니라, 아주 작은 ReAct loop를 직접 보면서 agent가 어떻게 도는지 확인합니다.
> 중요한 건 코드를 많이 치는 게 아니라, LLM 호출과 tool 호출이 어떻게 연결되고 trace에서 어떻게 보이는지 이해하는 것입니다.

작업 위치 확인:

```bash
pwd
```

기대 위치:

```text
.../kisa-ai-agent-practice
```

최신 코드 받기:

```bash
git pull origin main
```

---

## 1. 환경 확인

실행:

```bash
python3 check_env.py
```

정상 출력:

```text
✅ Gemini OK
✅ Langfuse OK
```

확인 포인트:

> Gemini는 모델 호출용이고, Langfuse는 agent 실행 과정을 기록하는 observability 도구입니다.
> 둘 중 하나라도 실패하면 뒤 실습이 제대로 안 됩니다.

문제 발생 시:

- `.env`가 repo root에 있는지 확인
- `GEMINI_API_KEY` 확인
- `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` 확인
- 로컬에서 `python`이 아니라 `python3` 사용

---

## 2. Step 1 — Baseline 실행

실행:

```bash
python3 agent.py
```

터미널에서 확인할 것:

```text
[Step 1]
  → search_db(...)
     ← ...

[Step 2]
Final answer: ...
```

진행 포인트:

> 지금 agent는 먼저 사용자 질문을 LLM에 보냅니다.
> LLM은 바로 답하지 않고 `search_db`라는 tool을 호출하겠다고 결정합니다.
> Python host application이 실제 `search_db` 함수를 실행하고, 그 결과를 다시 LLM에게 observation으로 넣습니다.
> 그 다음 LLM이 최종 답변을 만듭니다.

`agent.py`에서 같이 볼 위치:

- `TOOLS`
- `HANDLERS`
- `react_loop`
- `call_llm`
- `execute_tool`

개념 정리:

```text
TOOLS     = LLM에게 알려주는 tool schema
HANDLERS  = 실제 Python 함수 매핑
call_llm  = LLM decide 단계
execute_tool = host application의 tool 실행
react_loop = 전체 loop
```

### Langfuse에서 지금 보이는 현상

Langfuse Tracing 화면을 열면 다음처럼 보일 수 있습니다.

```text
llm.generate_content
tool.execute
llm.generate_content
```

즉, 큰 `react_loop` 하나 아래로 묶이지 않고 흩어져 보일 수 있습니다.

진행 포인트:

> 이 상태가 이상한 게 아닙니다.
> child span인 LLM call과 tool execution은 이미 찍히고 있지만, 전체 사용자 요청을 감싸는 parent span이 아직 없습니다.
> 그래서 지금은 한 요청의 lifecycle이 아니라 조각난 span처럼 보입니다.
> 이 문제를 Step 3에서 해결합니다.

비교 checkpoint:

```text
solutions/01_baseline.py
```

---

## 3. Step 2 — 두 번째 Tool 추가

목표:

> `search_db` 하나만 있던 agent에 `get_user_info(user_id)` tool을 추가합니다.

`agent.py`에서 TODO 1 찾기:

```python
# TODO 1 — Step 2: 두 번째 tool을 추가하세요.
```

### 3-1. 함수 추가

`search_db` 아래에 추가:

```python
def get_user_info(user_id: str) -> str:
    """user_id로 user 정보 조회 (mock)."""
    mock_users = {
        "u001": "name=Kim · team=Platform · role=Backend · joined=2024-03",
        "u002": "name=Lee · team=Data · role=Analyst · joined=2025-01",
        "u012": "name=Park · team=Platform · role=Frontend · joined=2025-08",
    }
    return mock_users.get(user_id, f"확인된 사용자 정보 없음: user_id='{user_id}'")
```

진행 포인트:

> 이 함수는 그냥 Python 함수입니다.
> LLM이 직접 이 함수를 실행하는 게 아니라, LLM은 function call 요청만 만들고 Python 코드가 실행합니다.

### 3-2. `TOOLS`에 schema 추가

`TOOLS` 배열 안에 추가:

```python
types.FunctionDeclaration(
    name="get_user_info",
    description="user_id로 사용자 정보 조회 (이름·팀·역할·입사일)",
    parameters=types.Schema(
        type=types.Type.OBJECT,
        properties={
            "user_id": types.Schema(
                type=types.Type.STRING,
                description="조회할 사용자 ID, 예: 'u001'",
            ),
        },
        required=["user_id"],
    ),
),
```

진행 포인트:

> 이 schema가 있어야 LLM이 `get_user_info`라는 tool의 존재와 argument 형태를 압니다.

### 3-3. `HANDLERS`에 매핑 추가

```python
HANDLERS = {
    "search_db": search_db,
    "get_user_info": get_user_info,
}
```

진행 포인트:

> schema는 LLM에게 보여주는 계약이고, HANDLERS는 실제 Python 실행 매핑입니다.
> 둘 중 하나라도 빠지면 agent가 깨집니다.

### 3-4. sample query 변경

`agent.py` 맨 아래에서 sample query를 잠깐 바꾸기:

```python
sample_query = "u001 사용자 정보와 production logs를 함께 알려줘"
```

실행:

```bash
python3 agent.py
```

기대 흐름 예시:

```text
→ get_user_info({'user_id': 'u001'})
→ search_db({'query': 'production logs'})
Final answer: ...
```

진행 포인트:

> 이제 모델이 질문을 보고 user 정보는 `get_user_info`, production 로그는 `search_db`로 나눠서 가져옵니다.
> agent에서 tool이 많아질수록 “어떤 tool을 언제 쓰는가”가 중요해집니다.

Langfuse에서 볼 것:

- `get_user_info`가 tool call로 찍히는지
- `search_db`도 같이 찍히는지
- 아직 parent trace가 없으면 span들이 흩어져 보일 수 있음

비교 checkpoint:

```text
solutions/02_add_tool.py
```

---

## 4. Step 3 — Parent observe로 nested trace 만들기

목표:

> 흩어져 보이던 LLM call과 tool call을 하나의 요청 아래로 묶습니다.

`agent.py`에서 TODO 2 찾기:

```python
# @langfuse.observe()  ← TODO 2: 이 줄 주석 해제
def react_loop(user_input: str, max_steps: int = 10) -> str:
```

이렇게 수정:

```python
@langfuse.observe()
def react_loop(user_input: str, max_steps: int = 10) -> str:
```

실행:

```bash
python3 agent.py
```

Langfuse에서 `react_loop` trace 클릭.

기대 구조:

```text
react_loop
  ├─ llm.generate_content
  ├─ tool.execute
  └─ llm.generate_content
```

진행 포인트:

> 이전에는 LLM call과 tool call이 각각 root trace처럼 보였습니다.
> 이제 `react_loop`가 parent span이 되면서 하나의 사용자 요청 lifecycle이 생깁니다.
> production에서 디버깅할 때는 이 구조가 중요합니다.
> 최종 답변이 이상하면, LLM이 tool을 잘못 골랐는지, tool input이 이상했는지, tool output은 맞는데 최종 답변만 틀렸는지 순서대로 추적할 수 있습니다.

비교 설명:

```text
Before:
llm.generate_content
tool.execute
llm.generate_content

After:
react_loop
 ├─ llm.generate_content
 ├─ tool.execute
 └─ llm.generate_content
```

비교 checkpoint:

```text
solutions/03_nested_trace.py
```

---

## 5. Step 3+ — Metadata 추가

목표:

> 여러 trace가 섞일 때 본인 실행을 찾기 쉽게 만듭니다.

`react_loop` 함수 시작 부분에 추가:

```python
@langfuse.observe()
def react_loop(user_input: str, max_steps: int = 10) -> str:
    langfuse.get_client().update_current_span(
        metadata={
            "user_id": "your_nickname",
            "tags": ["day1"],
        },
    )

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
```

실행:

```bash
python3 agent.py
```

Langfuse에서 확인:

- metadata
- tags
- user_id

진행 포인트:

> 실제 production에서는 user_id, tenant, endpoint, experiment name, release version 같은 값을 metadata로 붙입니다.
> 그래야 문제가 생겼을 때 특정 사용자, 특정 버전, 특정 실험군만 필터링해서 볼 수 있습니다.

비교 checkpoint:

```text
solutions/04_metadata.py
```

---

## 6. Step 4 — 실패 케이스 진단

목표:

> 실패를 그냥 터미널 에러로 보는 게 아니라, trace에서 어느 단계가 깨졌는지 찾습니다.

하나씩 실행:

```bash
python3 failures/bad_tool_demo.py
python3 failures/infinite_loop_demo.py
python3 failures/hallucination_demo.py
python3 failures/lazy_response_demo.py
```

각 시나리오마다 확인할 것:

```text
1. 어떤 tool이 호출됐나?
2. tool input은 맞나?
3. tool output은 맞나?
4. 최종 답변은 tool output에 근거했나?
5. 문제는 LLM 판단, tool wiring, prompt, stop condition 중 어디인가?
```

### 6-1. bad_tool_demo

기대 에러:

```text
Unknown tool: search_db
```

진행 포인트:

> 모델은 `search_db`를 호출했지만 Python 쪽 `HANDLERS` 매핑이 깨져 있습니다.
> 이건 모델 추론 문제가 아니라 application wiring 문제입니다.

### 6-2. infinite_loop_demo

기대 에러:

```text
max_steps exceeded
```

진행 포인트:

> final answer가 나오기 전에 loop budget이 끝났습니다.
> production agent에는 반드시 stop condition과 budget guard가 필요합니다.

### 6-3. hallucination_demo

관찰:

```text
tool output: 데이터 없음
final answer: 로그인 패턴, 디바이스, 세션 시간 등을 추측
```

진행 포인트:

> tool output에 없는 정보가 최종 답변에 들어가면 hallucination입니다.
> trace를 보면 그 정보가 어디서도 오지 않았다는 걸 증명할 수 있습니다.

### 6-4. lazy_response_demo

관찰:

```text
tool output: 정상 데이터
final answer: 분석하겠습니다.
```

진행 포인트:

> tool은 정상인데 final answer instruction이 잘못돼서 답변을 미뤘습니다.
> prompt는 예쁜 문구가 아니라 failure mode를 막는 guard입니다.

---

## 7. Step 5 — Golden Dataset 평가

실행:

```bash
python3 evaluate.py
```

출력 예시:

```text
=== Summary: N/6 passed (...) ===
Report written to .eval/latest.md and .eval/latest.json
```

N이 6보다 작아도 괜찮습니다. 이 단계의 목적은 "항상 통과"가 아니라, 어떤 case에서 agent가 약한지 report로 확인하는 것입니다.

모의 regression 확인:

```bash
python3 evaluate.py --simulate-regression
```

`edge-006-resist-user-pressure` 같은 case가 실패하면, 사용자가 추정을 요구할 때 agent가 tool evidence 밖의 일반 패턴을 말하는 문제를 eval이 잡아낸 것입니다.

진행 포인트:

> trace는 한 요청을 깊게 보는 도구이고, evaluation은 여러 hard case를 반복해서 보는 도구입니다.
> 여기서는 정답 문자열을 완전히 맞추는 게 아니라, tool 사용과 답변 의미를 평가합니다.
> `must_call_tools`는 deterministic check이고, `rubric`은 LLM-as-Judge가 자연어 답변을 판정합니다.

추가 과제:

`golden_set.yaml`에 본인 case 하나 추가:

```yaml
- id: my-001
  input: <본인이 만든 질문>
  expected:
    must_call_tools: ["search_db"]
    max_tool_calls: 2
    min_score: 5
    rubric:
      correctness: 답변이 만족해야 하는 사실 조건을 적습니다.
      grounding: tool 결과에 없는 추측을 하면 실패라고 적습니다.
      completeness: 질문에 모두 답했는지 기준을 적습니다.
  notes: 어떤 실패를 잡으려는지
```

재실행:

```bash
python3 evaluate.py
```

---

## 자주 헷갈리는 포인트

### Q1. 왜 처음에는 trace가 하나로 안 묶이나요?

답변:

> `call_llm`과 `execute_tool`에는 이미 `@langfuse.observe`가 붙어 있어서 각각 기록됩니다.
> 하지만 전체 요청을 감싸는 `react_loop`에는 아직 parent observe가 없기 때문에 root trace처럼 흩어져 보입니다.
> Step 3에서 `react_loop`에 `@langfuse.observe()`를 붙이면 nested trace로 묶입니다.

### Q2. LLM이 tool을 직접 실행하나요?

답변:

> 아닙니다. LLM은 “이 tool을 이런 args로 호출하고 싶다”는 structured request를 만듭니다.
> 실제 실행은 Python host application이 `HANDLERS`를 보고 합니다.

### Q3. `TOOLS`와 `HANDLERS` 둘 다 왜 필요한가요?

답변:

> `TOOLS`는 LLM에게 보여주는 API 문서입니다.
> `HANDLERS`는 실제 Python 함수 연결입니다.
> schema만 있고 handler가 없으면 호출은 되지만 실행이 안 됩니다.
> handler만 있고 schema가 없으면 LLM이 그 tool의 존재를 모릅니다.

### Q4. `langfuse.get_client()`는 Gemini client인가요?

답변:

> 아닙니다. `langfuse.get_client()`는 Langfuse trace client입니다.
> Gemini 호출용 client는 `genai.Client(...)`로 따로 만듭니다.
> 그래서 코드에서 `import langfuse` namespace를 사용해 헷갈리지 않게 했습니다.

### Q5. 답이 매번 조금씩 다른데 괜찮나요?

답변:

> 네. 자연어 표현은 달라질 수 있습니다.
> 그래서 evaluation은 완전 일치가 아니라 tool 호출 여부, 반드시 언급해야 할 정보, 말하면 안 되는 정보를 기준으로 봅니다.

---

## 빠른 복구표

| 상황 | 비교 파일 |
|---|---|
| 시작 상태가 꼬임 | `solutions/01_baseline.py` |
| tool 추가에서 막힘 | `solutions/02_add_tool.py` |
| nested trace가 안 됨 | `solutions/03_nested_trace.py` |
| metadata 위치를 모름 | `solutions/04_metadata.py` |
| 최종 전체 코드 필요 | `solutions/agent.py` |

---

## 마무리

> 오늘 한 실습은 작지만 production agent의 핵심 구조가 다 들어 있습니다.
> LLM call, tool call, orchestration loop, observability, failure diagnosis, evaluation입니다.
> 앞으로 agent를 더 복잡하게 만들더라도 디버깅 순서는 같습니다.
> “모델이 뭘 봤나 → 어떤 tool을 불렀나 → tool이 뭘 돌려줬나 → 최종 답변이 근거를 지켰나”를 trace로 확인하면 됩니다.
