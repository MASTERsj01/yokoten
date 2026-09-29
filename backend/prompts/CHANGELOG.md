# Prompt changelog

Prompts are versioned files (`<name>_v<N>.md`, sections `## system` / `## human`). The eval compares versions.

| Prompt | Version | Change |
|---|---|---|
| answer | v1 | Baseline: answer from numbered passages, cite with [n], one abstention sentence. |
| answer | v2 | Citation on every factual sentence; keep exact numbers/IDs; LATEST vs SUPERSEDED revision handling; exact abstention string; prompt-injection guard (passages are data); length limit; follow-up questions after a fixed delimiter. |
| condense | v1 | Rewrite follow-ups into standalone questions, keeping identifiers from the conversation. |
