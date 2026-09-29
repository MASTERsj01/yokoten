"""Four chunking strategies over the loader's layout elements (compared in the eval ablation).

fixed        fixed-size word windows over the flattened text (ignores structure)
recursive    LangChain RecursiveCharacterTextSplitter over the flattened text
structure    one chunk per section / table / figure / spreadsheet row (long sections split recursively)
parent_child small child chunks are indexed; their parent section is what the LLM sees (small-to-big)
"""

from dataclasses import dataclass, field

from langchain_core.documents import Document as LCDocument
from langchain_text_splitters import CharacterTextSplitter, RecursiveCharacterTextSplitter

STRATEGIES = ("fixed", "recursive", "structure", "parent_child")
SIZE = {
    "fixed": (800, 100),
    "recursive": (800, 120),
    "structure": (1200, 150),
    "parent": (2000, 200),
    "child": (380, 60),
}


@dataclass
class ChunkOut:
    text: str
    kind: str
    section: str
    page: int | None
    bboxes: list = field(default_factory=list)
    idx: int = 0
    parent_idx: int | None = None  # index of the parent chunk (parent_child only)
    indexed: bool = True


def _loc(els: list[LCDocument]) -> tuple[int | None, list]:
    pages = [e.metadata.get("page") for e in els if e.metadata.get("page")]
    bboxes = [
        [e.metadata["page"], *e.metadata["bbox"]]
        for e in els
        if e.metadata.get("bbox") and e.metadata.get("page")
    ]
    return (pages[0] if pages else None), bboxes


def _flatten(els: list[LCDocument]) -> tuple[str, list[tuple[int, int, int]]]:
    parts, spans, pos = [], [], 0
    for i, e in enumerate(els):
        t = e.page_content
        spans.append((pos, pos + len(t), i))
        parts.append(t)
        pos += len(t) + 2
    return "\n\n".join(parts), spans


def _by_offset(els, splitter) -> list[ChunkOut]:
    text, spans = _flatten(els)
    out = []
    for d in splitter.create_documents([text]):
        start = d.metadata.get("start_index", 0)
        end = start + len(d.page_content)
        hit = [els[i] for s, e, i in spans if s < end and e > start]
        page, bboxes = _loc(hit)
        section = hit[0].metadata.get("section", "") if hit else ""
        out.append(ChunkOut(d.page_content, "text", section, page, bboxes))
    return out


def _sections(els: list[LCDocument]) -> list[tuple[str, str, list[LCDocument]]]:
    """Group consecutive elements into (kind, section, elements); tables, figures, rows and OCR stay atomic units."""
    groups: list[tuple[str, str, list]] = []
    for e in els:
        kind, section = e.metadata["kind"], e.metadata.get("section", "")
        if kind in ("table", "figure", "row"):
            groups.append((kind, section, [e]))
        elif kind == "heading" or not groups or groups[-1][0] != "text" or groups[-1][1] != section:
            groups.append(("text", section, [e]))
        else:
            groups[-1][2].append(e)
    return groups


def _structure(els, size: tuple[int, int]) -> list[ChunkOut]:
    split = RecursiveCharacterTextSplitter(chunk_size=size[0], chunk_overlap=size[1])
    out = []
    for kind, section, group in _sections(els):
        text = "\n".join(e.page_content for e in group)
        page, bboxes = _loc(group)
        if kind in ("text",) and len(text) > size[0]:
            out += [ChunkOut(t, kind, section, page, bboxes) for t in split.split_text(text)]
        elif text.strip():
            out.append(ChunkOut(text, kind, section, page, bboxes))
    return out


def chunk(els: list[LCDocument], strategy: str) -> list[ChunkOut]:
    els = [e for e in els if e.page_content.strip()]
    if strategy == "fixed":
        chunks = _by_offset(
            els,
            CharacterTextSplitter(
                separator=" ",
                chunk_size=SIZE["fixed"][0],
                chunk_overlap=SIZE["fixed"][1],
                add_start_index=True,
            ),
        )
    elif strategy == "recursive":
        chunks = _by_offset(
            els,
            RecursiveCharacterTextSplitter(
                chunk_size=SIZE["recursive"][0], chunk_overlap=SIZE["recursive"][1], add_start_index=True
            ),
        )
    elif strategy == "structure":
        chunks = _structure(els, SIZE["structure"])
    elif strategy == "parent_child":
        child_split = RecursiveCharacterTextSplitter(
            chunk_size=SIZE["child"][0], chunk_overlap=SIZE["child"][1]
        )
        chunks = []
        for parent in _structure(els, SIZE["parent"]):
            kind = parent.kind
            parent.kind, parent.indexed = "parent", False
            parent_idx = len(chunks)
            chunks.append(parent)
            pieces = (
                [parent.text] if len(parent.text) <= SIZE["child"][0] else child_split.split_text(parent.text)
            )
            for t in pieces:
                chunks.append(
                    ChunkOut(t, kind, parent.section, parent.page, parent.bboxes, parent_idx=parent_idx)
                )
    else:
        raise ValueError(strategy)
    for i, c in enumerate(chunks):
        c.idx = i
    return chunks
