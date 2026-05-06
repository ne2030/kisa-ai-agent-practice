# Step별 정답 / Checkpoint

실습은 `agent.py` 하나를 점진적으로 바꿔가며 진행합니다. 이 폴더의 파일은 막혔을 때 필요한 단계만 비교하기 위한 checkpoint입니다.

## 진행 시나리오

| 단계 | 실행/비교 파일 | 코드 변화 | Langfuse에서 보이는 것 |
|---|---|---|---|
| Step 1 baseline | `solutions/01_baseline.py` | `search_db` 하나로 ReAct loop가 동작 | parent `react_loop`가 아직 없어 `llm.generate_content`, `tool.execute`가 목록에서 따로 보일 수 있음 |
| Step 2 tool 추가 | `solutions/02_add_tool.py` | `get_user_info` 추가. 모델이 상황에 따라 tool을 고름 | 여전히 child span이 root trace처럼 흩어질 수 있음. “왜 묶이지 않지?” 질문 유도 |
| Step 3 parent observe | `solutions/03_nested_trace.py` | `react_loop`에 `@langfuse.observe()` 한 줄 추가 | `react_loop` 하나 아래 `llm.generate_content` → `tool.execute` → `llm.generate_content`가 nested로 묶임 |
| Step 4 metadata | `solutions/04_metadata.py` | `langfuse.get_client().update_current_span(metadata=...)` 추가 | trace tree는 같고, metadata/tags/user_id로 본인 실행을 찾기 쉬워짐 |
| Final | `solutions/agent.py` | TODO 1, 2가 모두 반영된 최종본 | Step 4와 같은 최종 참고용 |

## 핵심 흐름

1. **처음에는 terminal 중심**으로 loop를 이해한다.
2. Langfuse 목록에 `llm.generate_content`와 `tool.execute`가 따로 보이면 오히려 좋다.
   “지금은 parent span이 없어서 한 요청으로 묶이지 않는다”는 문제를 보여준다.
3. `react_loop`에 `@langfuse.observe()`를 붙이면 한 요청의 lifecycle이 parent trace로 생긴다.
4. 그 안에 LLM call과 tool execution이 child span으로 들어간다.
5. 마지막으로 metadata를 붙여 production에서 trace를 검색/필터링하는 감각을 보여준다.

## 권장 공개 순서

- 시작 전: `solutions/` 폴더는 “막혔을 때만 보는 비교용”으로 안내
- Step 2 후: `02_add_tool.py`만 공개 가능
- Step 3 후: `03_nested_trace.py` 공개
- 끝난 뒤: `04_metadata.py`, `agent.py` 공개
