# ADR 0001: The LLM never produces a number

- **Status:** Accepted (recorded retroactively)
- **Date of the decision:** 2026-08-10
- **Deciders:** Renan Maciel

## Context

B.I.A. is the WhatsApp assistant used by the battalion's command staff. It answers questions such as "how many personnel are available today?" or "who is on duty at the south station?" through an n8n agent that calls the dashboard API as tools.

The first version returned raw rows from the tools and let the model format the answer. Measured with the evaluation harness in [`avaliacao_llm/`](../../avaliacao_llm/), the model invented figures in roughly 12% of the questions, including plausible ones such as "0 divers". For a command staff that makes staffing decisions from these answers, a plausible wrong number is worse than no answer.

## Decision

1. **Every assistant tool returns the final text.** Each `/consulta/*` endpoint in [`webapp/routers/consulta.py`](../../webapp/routers/consulta.py) returns a `mensagem` field already rendered in the WhatsApp house style (emoji, bold, `dd/mm/yyyy` dates). Every number in it comes from a database query.
2. **The model relays, it does not compose.** The agent's system prompt instructs it to repeat `mensagem` verbatim. The model chooses which tool to call and with which arguments; it never formats or computes data.
3. **Behaviour is measured, not assumed.** Model and prompt changes are evaluated with the harness, which has dedicated tests for hallucinated numbers, invented names, tool failures, context overflow, the memory window and multi-turn follow-ups. The prompt went through several measured iterations (`system_prompt_v3.txt` to `system_prompt_v10.txt`).

## Consequences

### Positive

- Numbers shown to the command staff are as correct as the database, which is auditable.
- Formatting rules live in Python, where they are tested, instead of in a prompt.
- Smaller local models (served by Ollama) become viable, because the model's job is reduced to selecting tools.

### Negative / Trade-offs

- Every new kind of question needs a new tool or a new rendering in the API; the assistant cannot answer what no tool covers.
- Answers are less conversational, because the text is fixed by the API.

## References

- [`webapp/routers/consulta.py`](../../webapp/routers/consulta.py): the tool contract and the rationale comment
- [`avaliacao_llm/`](../../avaliacao_llm/): evaluation harness and prompt versions
