"""P6: text-to-SQL safety (K), role-based access (N), SME verification loop (M)."""

import pytest

from yokoten.rag.sql import SqlError, check_answer, extract_sql


def test_extract_sql_accepts_select_and_strips_fences():
    assert extract_sql("```sql\nSELECT COUNT(*) FROM docs;\n```") == "SELECT COUNT(*) FROM docs"
    assert extract_sql("Here you go: WITH x AS (SELECT 1) SELECT * FROM x").startswith("WITH")


@pytest.mark.parametrize(
    "bad",
    [
        "DROP TABLE document",
        "SELECT 1; DELETE FROM document",
        "UPDATE docs SET x=1",
        "SELECT * FROM docs; ATTACH 'x' AS y",
        "no sql here",
    ],
)
def test_extract_sql_rejects_writes_and_multiple_statements(bad):
    with pytest.raises(SqlError):
        extract_sql(bad)


def test_sql_answer_consistency_check():
    info = {"rows": [[4]], "columns": ["n"]}
    assert (
        check_answer("There are 4 8D reports for inverters.", info)["faithfulness"] == 1.0
    )  # '8D' is not a number
    assert (
        check_answer("There were 4 reports in 2022.", info)["faithfulness"] == 0.5
    )  # 2022 is not in the result
