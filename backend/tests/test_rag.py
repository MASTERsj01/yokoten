from yokoten.rag.pipeline import confidence, split_sentences
from yokoten.rag.query import condense, expand, extract_filters, load_prompt


def test_filters_from_question():
    f = extract_filters("Which traction inverter lessons learned were recorded after 2022?")
    assert f == {"year_min": 2023, "component": ["INV"], "doc_type": ["lessons_learned"]}
    assert extract_filters("Which 8D reports were opened at the Toluca Plant in 2023?") == {
        "year_min": 2023,
        "year_max": 2023,
        "plant": ["TLC"],
        "doc_type": ["8d"],
    }
    # doc-type filters only for list-style questions, so multi-hop questions keep their other hops
    assert "doc_type" not in extract_filters("In the DFMEA, what action priority did the failure mode have?")
    assert extract_filters("What was the root cause?") == {}


def test_acronym_and_synonym_expansion():
    q, added = expand("What PPM did the supplier have?")
    assert "parts per million defect rate" in added and "vendor" in added and q.startswith("What PPM")


def test_condense_heuristic_without_llm():
    history = [
        {"role": "user", "content": "What happened with the DC-DC output ripple on P-DCD-2102?"},
        {"role": "assistant", "content": "Ripple of 450 mV."},
    ]
    q, method = condense("What was the root cause?", history, None, None)
    assert method == "heuristic" and "P-DCD-2102" in q and q.endswith("What was the root cause?")


def test_prompt_files_parse():
    for version in ("v1", "v2"):
        msgs = load_prompt("answer", version).format_messages(context="[1] x", question="q?")
        assert msgs[0].type == "system" and "q?" in msgs[1].content


def test_sentence_split_and_confidence():
    s = split_sentences(
        "The root cause was voiding [1]. It was fixed with sintered silver [2][3].\n- Short list item here"
    )
    assert len(s) == 3
    assert confidence(1.0, 1.0) == (1.0, "high") and confidence(0.2, 0.0)[1] == "low"
