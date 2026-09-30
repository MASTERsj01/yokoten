"""NHTSA recalls (US Government work, public domain) -> a separate 'public_recalls' collection + small eval subset.

Source: https://static.nhtsa.gov/odi/ffdd/rcl/FLAT_RCL_POST_2010.zip (field list in RCL.txt).
One document per recall campaign; filtered to component systems that match the product lines in this project.
Campaigns mentioning DENSO are excluded (project rule: no real-company demo content about that company).
"""

import csv
import io
import json
import random
import re
import zipfile
from collections import defaultdict
from pathlib import Path

URL = "https://static.nhtsa.gov/odi/ffdd/rcl/FLAT_RCL_POST_2010.zip"
FIELDS = [
    "RECORD_ID",
    "CAMPNO",
    "MAKETXT",
    "MODELTXT",
    "YEARTXT",
    "MFGCAMPNO",
    "COMPNAME",
    "MFGNAME",
    "BGMAN",
    "ENDMAN",
    "RCLTYPECD",
    "POTAFF",
    "ODATE",
    "INFLUENCED_BY",
    "MFGTXT",
    "RCDATE",
    "DATEA",
    "RPNO",
    "FMVSS",
    "DESC_DEFECT",
    "CONEQUENCE_DEFECT",
    "CORRECTIVE_ACTION",
    "NOTES",
    "RCL_CMPT_ID",
    "MFR_COMP_NAME",
    "MFR_COMP_DESC",
    "MFR_COMP_PTNO",
    "DO_NOT_DRIVE",
    "PARK_OUTSIDE",
]
# NHTSA component systems -> this project's product lines
SYSTEMS = {
    "ENGINE AND ENGINE COOLING": "thermal",
    "EQUIPMENT:OTHER:AIR CONDITIONING": "thermal",
    "FUEL SYSTEM": "powertrain",
    "POWER TRAIN": "powertrain",
    "ELECTRICAL SYSTEM": "electrification",
    "STEERING": "body_electronics",
    "VISIBILITY:WINDSHIELD WIPER": "body_electronics",
}
EXCLUDE = re.compile(r"denso", re.I)


def _line(compname: str) -> str | None:
    for prefix, line in SYSTEMS.items():
        if compname.startswith(prefix):
            return line
    return None


def load_campaigns(zip_path: Path, min_year: int = 2021) -> dict[str, dict]:
    campaigns: dict[str, dict] = {}
    models: dict[str, set] = defaultdict(set)
    with zipfile.ZipFile(zip_path) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".txt"))
        with z.open(name) as f:
            reader = csv.reader(
                io.TextIOWrapper(f, encoding="latin-1"), delimiter="\t", quoting=csv.QUOTE_NONE
            )
            for row in reader:
                if len(row) < 23:
                    continue
                r = dict(zip(FIELDS, row, strict=False))
                year = int(r["RCDATE"][:4]) if r["RCDATE"][:4].isdigit() else 0
                line = _line(r["COMPNAME"])
                if year < min_year or not line or r["RCLTYPECD"] != "V":
                    continue
                if EXCLUDE.search(" ".join(row)):
                    campaigns.pop(r["CAMPNO"], None)
                    models.pop(r["CAMPNO"], None)
                    continue
                models[r["CAMPNO"]].add(f"{r['MAKETXT']} {r['MODELTXT']} {r['YEARTXT']}".strip())
                c = campaigns.setdefault(
                    r["CAMPNO"], {**r, "year": year, "product_line": line, "components": set()}
                )
                c["components"].add(r["COMPNAME"])
    for k, c in campaigns.items():
        c["models"] = sorted(models[k])
    return campaigns


def _doc(c: dict) -> str:
    comps = sorted(c["components"])
    date = f"{c['RCDATE'][:4]}-{c['RCDATE'][4:6]}-{c['RCDATE'][6:8]}"
    lines = [
        f"# NHTSA recall {c['CAMPNO']}: {comps[0].title()}",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Campaign | {c['CAMPNO']} |",
        f"| Report received | {date} |",
        f"| Manufacturer | {c['MFGNAME']} |",
        f"| Component | {'; '.join(comps)} |",
        f"| Potential units affected | {c['POTAFF'] or 'not stated'} |",
        f"| Recall initiated by | {c['INFLUENCED_BY']} |",
        "",
        "## Vehicles",
        "",
        ", ".join(c["models"][:12]) + (" and others" if len(c["models"]) > 12 else ""),
        "",
        "## Defect",
        "",
        c["DESC_DEFECT"].strip(),
        "",
        "## Consequence",
        "",
        c["CONEQUENCE_DEFECT"].strip(),
        "",
        "## Remedy",
        "",
        c["CORRECTIVE_ACTION"].strip(),
        "",
    ]
    if c["NOTES"].strip():
        lines += ["## Notes", "", c["NOTES"].strip(), ""]
    lines += ["*Source: NHTSA recalls flat file (public domain).*"]
    return "\n".join(lines)


def build(zip_path: Path, out_dir: Path, eval_path: Path, n: int = 1500, seed: int = 42) -> dict:
    campaigns = load_campaigns(zip_path)
    keys = sorted(campaigns)
    rng = random.Random(seed)
    chosen = sorted(rng.sample(keys, min(n, len(keys))))
    docs_dir = out_dir / "recalls"
    docs_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for k in chosen:
        c = campaigns[k]
        (docs_dir / f"{k}.md").write_text(_doc(c), "utf-8")
        manifest.append(
            {
                "doc_id": f"NHTSA-{k}",
                "title": f"NHTSA recall {k}: {sorted(c['components'])[0].title()}",
                "doc_type": "recall",
                "format": "md",
                "file": f"recalls/{k}.md",
                "year": c["year"],
                "date": c["RCDATE"],
                "product_line": c["product_line"],
                "classification": "public",
            }
        )
    (out_dir / "manifest.json").write_text(
        json.dumps({"source": URL, "documents": manifest}, indent=1), "utf-8"
    )
    # small eval subset: ID lookups + descriptive questions (no manufacturer names in the questions)
    qs = []
    pool = [k for k in chosen if campaigns[k]["POTAFF"].isdigit() and int(campaigns[k]["POTAFF"]) > 0]
    for i, k in enumerate(rng.sample(pool, 20)):
        c = campaigns[k]
        comp = sorted(c["components"])[0]
        top = comp.split(":")[0].title()
        if i < 10:
            qs.append(
                {
                    "id": f"P{i + 1:02d}",
                    "category": "public_lookup",
                    "question": f"How many vehicles are potentially affected by NHTSA recall {k}, and which "
                    f"component system is involved?",
                    "reference_answer": f"{int(c['POTAFF']):,} units; {comp}.",
                    "answer_facts": [c["POTAFF"], top.split()[0].lower()],
                    "gold": [[f"NHTSA-{k}"]],
                }
            )
        else:
            defect = re.sub(r"\s+", " ", c["DESC_DEFECT"]).strip()
            snippet = " ".join(defect.split()[:18])
            qs.append(
                {
                    "id": f"P{i + 1:02d}",
                    "category": "public_semantic",
                    "question": f'Which recall reported in {c["RCDATE"][:4]} describes this defect: "{snippet}..."?',
                    "reference_answer": f"NHTSA recall {k}.",
                    "answer_facts": [k.lower()],
                    "gold": [[f"NHTSA-{k}"]],
                }
            )
    eval_path.write_text("\n".join(json.dumps(q) for q in qs) + "\n", "utf-8")
    return {"campaigns_in_scope": len(campaigns), "documents": len(manifest), "eval_questions": len(qs)}
