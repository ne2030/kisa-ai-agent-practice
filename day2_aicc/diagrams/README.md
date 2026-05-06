# Day 2 diagram

Day 2 AICC/LangGraph 구조를 한 장으로 보는 Mermaid 파일이에요.

| file | purpose |
|---|---|
| `aicc_structure.mmd` / `.svg` | 전체 흐름, agent node 구분, read/write tool 경계 |

SVG를 다시 만들 때는 Mermaid CLI를 써요.

```bash
npx --yes @mermaid-js/mermaid-cli -i day2_aicc/diagrams/aicc_structure.mmd -o day2_aicc/diagrams/aicc_structure.svg
```
