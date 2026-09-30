"""Text-to-SQL for analytical questions (counts, rankings, FMEA filters) over structured tables.

The LLM writes one SELECT; it runs on a read-only connection against role-filtered TEMP views, so it can
neither modify data nor see documents the user's role may not read.
"""

import re
import sqlite3
import time

from yokoten.config import settings
from yokoten.domain import DOC_TYPE_LABEL, ROLE_ACCESS
from yokoten.ingest.entities import glossary
from yokoten.rag import llm
from yokoten.rag.query import load_prompt

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|detach|pragma|replace|vacuum|reindex)\b", re.I
)
MAX_ROWS = 50


class SqlError(ValueError):
    pass


def extract_sql(text: str) -> str:
    text = re.sub(r"^```(?:sql)?|```$", "", text.strip(), flags=re.I | re.M).strip()
    m = re.search(r"\b(with|select)\b.*", text, re.I | re.S)
    if not m:
        raise SqlError("no SELECT statement in the model output")
    sql = m.group(0).strip().rstrip(";").strip()
    if ";" in sql:
        raise SqlError("multiple statements are not allowed")
    if FORBIDDEN.search(sql):
        raise SqlError("only read-only SELECT queries are allowed")
    return sql


def _connect(role: str) -> sqlite3.Connection:
    db = (settings.var_dir / "yokoten.db").as_posix()
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
    allowed = ",".join(f"'{c}'" for c in ROLE_ACCESS.get(role, []))  # fixed vocabulary, not user input
    con.execute(f"""CREATE TEMP VIEW docs AS SELECT doc_id, title, doc_type, year, product_line, component, project,
                    plant, suppliers, revision, is_latest FROM document
                    WHERE status = 'ready' AND collection = 'engineering' AND classification IN ({allowed})""")
    con.execute(f"""CREATE TEMP VIEW fmea AS SELECT f.doc_id, f.fmea_type, f.component, f.plant, f.item, f.failure_mode,
                    f.effect, f.cause, f.severity, f.occurrence, f.detection, f.action_priority, f.recommended_action,
                    f.status, f.revised_occurrence, f.revised_detection, f.revised_action_priority
                    FROM fmeaitem f JOIN document d ON d.doc_id = f.doc_id AND d.revision = f.revision
                    WHERE f.is_latest = 1 AND d.classification IN ({allowed})""")
    deadline = time.time() + 3
    con.set_progress_handler(lambda: int(time.time() > deadline), 10_000)  # abort runaway queries
    return con


def run_sql(sql: str, role: str) -> tuple[list[str], list[list]]:
    con = _connect(role)
    try:
        cur = con.execute(f"SELECT * FROM ({sql}) LIMIT {MAX_ROWS}")
        cols = [c[0] for c in cur.description]
        return cols, [list(r) for r in cur.fetchall()]
    except sqlite3.Error as e:
        raise SqlError(f"SQL error: {e}") from e
    finally:
        con.close()


def generate_sql(question: str, provider: str, model: str) -> tuple[str, llm.LlmCall]:
    g = glossary()
    msgs = load_prompt("sql", "v1").format_messages(
        question=question,
        doc_types=", ".join(k for k in DOC_TYPE_LABEL if k not in ("recall", "other")),
        components=", ".join(f"{k} ({v['name']})" for k, v in g["components"].items()),
        product_lines=", ".join(g["product_lines"]),
        plants=", ".join(f"{k} ({v[0].title()})" for k, v in g["plants"].items()),
    )
    call = llm.invoke(msgs, provider, model, max_tokens=250)
    return extract_sql(call.text), call


def format_result(cols: list[str], rows: list[list]) -> str:
    if not rows:
        return "The query returned no rows."
    lines = [" | ".join(cols)] + [" | ".join("" if v is None else str(v) for v in r) for r in rows[:20]]
    more = f"\n({len(rows)} rows in total)" if len(rows) > 20 else ""
    return "\n".join(lines) + more
