"""Build every corpus document (as IR) and the golden Q&A set from the ground truth in world.py."""

import math
import random
import re
from collections import Counter, defaultdict

import numpy as np

from yokoten.datagen.render import Doc, figure_png
from yokoten.datagen.world import (
    CASES,
    COMPONENTS,
    EXTRA_FMEA,
    PEOPLE,
    PLANTS,
    PROJECT,
    PROJECTS,
    SUPPLIERS,
    WORK_INSTRUCTIONS,
    Case,
)

SQR_YEARS = (2022, 2023, 2024)

# keyword that identifies each case in a list-style answer (alternatives separated by "|")
TAGS = {
    "rad-braze-voids": "tube-to-header|braz",
    "rad-tank-crack": "tank",
    "rad-salt-corrosion": "corrosion",
    "hvc-blend-door": "blend door|actuator",
    "hvc-evap-odor": "odour|odor",
    "hvc-blower-noise": "whine|blower",
    "cmp-oring-leak": "o-ring|refrigerant",
    "cmp-pd-insulation": "insulation|partial discharge",
    "cmp-scroll-wear": "scroll",
    "inj-coking": "coking",
    "inj-coil-open": "coil",
    "inj-oring-squeeze": "seepage|o-ring",
    "sns-egt-drift": "egt|drift",
    "sns-map-water": "map sensor|water ingress",
    "sns-fretting": "fretting",
    "inv-solder-fatigue": "solder",
    "inv-dclink-cap": "capacitor",
    "inv-emc": "emission|emc",
    "inv-desat": "desaturation",
    "dcd-mlcc-crack": "mlcc",
    "dcd-core-crack": "ferrite|core crack",
    "dcd-ripple": "ripple",
    "bms-voltage-drift": "voltage",
    "bms-can-loss": "can communication|can bus|bci",
    "bms-pin-pushout": "push-out|pushout",
    "bms-watchdog": "watchdog|ota",
    "wpm-gear-wear": "gear",
    "wpm-water": "water ingress|vent",
    "wpm-park-switch": "park switch",
    "eps-torque-ripple": "torque ripple|cogging|notchy",
    "eps-hall-eos": "hall",
    "eps-bearing-grease": "bearing",
}
FFA_RETURNS = {
    "rad-tank-crack": 118,
    "inj-coking": 26,
    "sns-egt-drift": 19,
    "inv-solder-fatigue": 41,
    "wpm-gear-wear": 58,
    "eps-hall-eos": 9,
}
INTERIM_TR = {"rad-tank-crack", "inv-solder-fatigue"}  # test reports with a superseded interim Rev A
PROCESS_STEP = {
    "rad-braze-voids": "Controlled-atmosphere brazing",
    "inj-coil-open": "Coil winding",
    "sns-map-water": "Connector seal assembly",
    "wpm-water": "Vent membrane welding",
    "dcd-mlcc-crack": "PCB depaneling",
}
GENERIC_TESTS = {
    "thermal": [
        ("Thermal shock", "NAS-TS-0120", "-40 C / +125 C, 30 min dwell", "no leak, no crack"),
        ("Vibration", "ISO 16750-3", "random, 8 h per axis", "no crack, no leak"),
        ("Neutral salt spray", "ISO 9227", "NSS 480 h", "no red rust, no perforation"),
        ("Burst pressure", "NAS-TS-0430", "hydraulic ramp", "burst above 4 bar"),
    ],
    "powertrain": [
        ("Thermal shock", "NAS-TS-0120", "-40 C / +150 C, 15 min dwell", "function within spec"),
        ("Vibration", "ISO 16750-3", "sine + random, 22 h per axis", "no failure"),
        ("Chemical resistance", "ISO 16750-5", "fuel, oil, coolant, salt", "no degradation"),
        ("Salt spray", "ISO 9227", "NSS 240 h", "function within spec"),
    ],
    "electrification": [
        ("Thermal shock", "NAS-TS-0120", "-40 C / +105 C, 1,000 cycles", "function within spec"),
        ("Vibration", "ISO 16750-3", "random, 22 h per axis", "no failure"),
        ("EMC radiated emissions", "CISPR 25 Class 3", "ALSE 30-1,000 MHz", "below limit"),
        ("EMC immunity", "ISO 11452-2", "200 V/m", "status A"),
        ("Damp heat", "IEC 60068-2-78", "85 C / 85% RH, 1,000 h", "function within spec"),
    ],
    "body_electronics": [
        ("Thermal shock", "NAS-TS-0120", "-40 C / +85 C, 500 cycles", "function within spec"),
        ("Vibration", "ISO 16750-3", "random, 8 h per axis", "no failure"),
        ("Water ingress", "ISO 20653", "IPX5 spray", "no water inside"),
        ("Endurance", "NAS-TS-1100", "rated load cycling", "function within spec"),
    ],
}
DRAWINGS = [
    (
        "RAD",
        "RAD-30512",
        "Outlet tank",
        "PA66-GF35",
        "Black, as moulded",
        "C",
        "1:2",
        "NO WELD LINE WITHIN 10 MM OF NECK",
    ),
    (
        "HVC",
        "HVC-33015",
        "Blend door",
        "PP-T20",
        "Grained VDI 3400 ref 27",
        "B",
        "1:1",
        "FLATNESS 0.5 MM MAX",
    ),
    (
        "CMP",
        "CMP-42008",
        "Motor housing",
        "EN AC-46000 AlSi9Cu3",
        "Machined bores Ra 1.6",
        "E",
        "1:2",
        "POROSITY CLASS 2 PER VDG P202",
    ),
    ("INJ", "INJ-53102", "Injector body", "X5CrNi18-10", "Passivated", "D", "2:1", "BURR HEIGHT 0.05 MM MAX"),
    (
        "SNS",
        "SNS-62007",
        "Sensor bracket",
        "DC04 ZnNi 8 UM",
        "Passivated, black",
        "B",
        "1:1",
        "SALT SPRAY 720 H NO RED RUST",
    ),
    (
        "INV",
        "INV-73110",
        "DC busbar positive",
        "Cu-ETP CW004A",
        "Tin plated 5 UM",
        "D",
        "1:1",
        "BEND RADIUS 3 MM MIN",
    ),
    (
        "DCD",
        "DCD-81006",
        "Cold plate",
        "EN AW-6063 T6",
        "Anodised 15 UM",
        "C",
        "1:2",
        "LEAK RATE 0.5 CC/MIN MAX AT 3 BAR",
    ),
    ("BMS", "BMS-91020", "ECU housing cover", "PA6-GF30 V0", "Natural", "B", "1:1", "UL94 V-0 AT 1.5 MM"),
    ("WPM", "WPM-12050", "Gearbox cover", "PBT-GF30", "Black", "F", "1:1", "WELD SEAM PULL-OFF 400 N MIN"),
    (
        "EPS",
        "EPS-13022",
        "Rotor shaft",
        "42CrMo4 QT",
        "Induction hardened 52-58 HRC",
        "C",
        "2:1",
        "RUNOUT 0.02 MM MAX",
    ),
]
INSPECTIONS = [
    (
        "CHN",
        "TAL",
        "RAD-20417",
        "Tube stock coil",
        "T-24-0381",
        2024,
        [
            ("Zinc load (XRF)", "8-10 g/m2", "8.6 g/m2", "OK"),
            ("Wall thickness", "0.27 +/- 0.02 mm", "0.28 mm", "OK"),
            ("Clad ratio", "10 +/- 2 %", "10.4 %", "OK"),
        ],
        "ACCEPT",
    ),
    (
        "CHN",
        "APD",
        "INV-70455",
        "SiC power module",
        "A-23-2210",
        2023,
        [
            ("Die-attach voids (X-ray)", "max 5 %", "2.1 %", "OK"),
            ("Isolation test", "4.2 kV 1 s", "pass", "OK"),
            ("Baseplate flatness", "max 100 um", "64 um", "OK"),
        ],
        "ACCEPT",
    ),
    (
        "KRK",
        "SCS",
        "CMP-40318",
        "HNBR housing O-ring",
        "S-23-1177",
        2023,
        [
            ("Hardness", "70 +/- 5 Shore A", "72 Shore A", "OK"),
            ("Compression set 70 h", "max 25 %", "31 %", "NG"),
            ("Cross-section", "2.62 +/- 0.08 mm", "2.63 mm", "OK"),
        ],
        "REJECT",
    ),
    (
        "TLC",
        "VLX",
        "RAD-22950",
        "PA66-GF30 inlet tank",
        "V-23-0452",
        2023,
        [
            ("Burst pressure", "min 4.5 bar", "6.8 bar", "OK"),
            ("Neck wall thickness", "2.5 +/- 0.2 mm", "2.6 mm", "OK"),
            ("Glass fibre content", "30 +/- 2 %", "29.5 %", "OK"),
        ],
        "ACCEPT",
    ),
    (
        "KRK",
        "MWC",
        "SNS-60140",
        "Silver-plated terminals",
        "M-24-0098",
        2024,
        [
            ("Plating thickness", "min 2 um", "2.7 um", "OK"),
            ("Insertion force", "max 15 N", "11.2 N", "OK"),
            ("Retention force", "min 50 N", "68 N", "OK"),
        ],
        "ACCEPT",
    ),
    (
        "TLC",
        "QTC",
        "INV-72031",
        "DC-link film capacitor",
        "Q-24-0613",
        2024,
        [
            ("Capacitance", "500 uF +/- 5 %", "503 uF", "OK"),
            ("ESR at 10 kHz", "max 0.6 mohm", "0.48 mohm", "OK"),
            ("Leakage current", "max 1 mA", "0.3 mA", "OK"),
        ],
        "ACCEPT",
    ),
    (
        "TLC",
        "CBR",
        "EPS-12315",
        "Rear ball bearing",
        "C-24-0327",
        2024,
        [
            ("Grease type (FTIR)", "per drawing: PAO/Li", "ester/Li", "NG"),
            ("Radial play", "6-14 um", "9 um", "OK"),
            ("Noise (Anderon)", "max 2.5", "1.8", "OK"),
        ],
        "REJECT",
    ),
    (
        "KRK",
        "HLS",
        "SNS-60102",
        "EGT sensing element",
        "H-22-1945",
        2022,
        [
            ("Insulation resistance 500 C", "min 5 Mohm", "21 Mohm", "OK"),
            ("R0 (Pt200)", "200 +/- 0.4 ohm", "200.2 ohm", "OK"),
            ("Moisture (MgO)", "max 0.1 %", "0.04 %", "OK"),
        ],
        "ACCEPT",
    ),
]
UNANSWERABLE = [
    "What was the root cause of the headlamp condensation issue on project P-RAD-2101?",
    "Which supplier provides the airbag inflators, and what is their PPM?",
    "What was the warranty cost in US dollars of the inverter solder fatigue issue?",
    "What did the 8D for the radiator coolant leak at the Krakow plant in 2019 conclude?",
    "What is the part number of the turbocharger actuator used on Halden Trucks?",
    "Who approved ECN-2020-001?",
    "What corrective action was taken after the BMS thermal runaway incident?",
    "How many fuel injectors failed the salt spray test in 2019?",
    "What is the tensile strength of the brazing sheet supplied by Talvik Alloys?",
    "What is the delivery lead time for Ardent Power Devices SiC modules?",
    "What was the root cause of the DC-DC converter fire in 2022?",
    "What were the results of the crash test on the HVAC module?",
    "What is the recommended coolant mixture ratio for the radiator?",
    "Which firmware version fixed the BMS CAN communication loss?",
    "Which plant builds the EPS motor for Kairo EV?",
    "What was the annual PPM of Castell Bearings in 2021?",
    "What was the root cause of the electric compressor clutch slip?",
    "When is the SOP of the 1,200 V inverter project?",
    "Which OEM reported a steering wheel vibration issue on the Halden Trucks EPS program?",
    "What torque is specified for the radiator drain plug in the work instructions?",
]
ROLES_8D = [
    "Champion",
    "Quality engineer",
    "Design engineer",
    "Process engineer",
    "Supplier quality engineer",
]


def action_priority(s: int, o: int, d: int) -> str:
    """AIAG-VDA style action priority (simplified lookup)."""
    if s >= 9:
        if o >= 4:
            return "H" if (d > 1 or o >= 6) else "M"
        if o >= 2:
            return "H" if d >= 7 else ("M" if d >= 5 else "L")
        return "L"
    if s >= 7:
        if o >= 8:
            return "H"
        if o >= 6:
            return "H" if d >= 2 else "M"
        if o >= 4:
            return "H" if d >= 7 else "M"
        if o >= 2:
            return "M" if d >= 5 else "L"
        return "L"
    if s >= 4:
        if o >= 8:
            return "H" if d >= 5 else "M"
        if o >= 6:
            return "M" if d >= 2 else "L"
        if o >= 4:
            return "M" if d >= 7 else "L"
        return "L"
    return "M" if (o >= 8 and d >= 5) else "L"


AP_WORD = {"H": "high|AP H|AP: H|(H)", "M": "medium|AP M|AP: M|(M)", "L": "low|AP L|AP: L|(L)"}


def num_facts(answer: str) -> list[str]:
    nums = re.findall(r"\d[\d,]*(?:\.\d+)?", answer)
    return [n.replace(",", "") for n in nums] or [answer.lower()]


class Corpus:
    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)
        self.docs: list[Doc] = []
        self.qs: list[dict] = []
        self.ids: dict[str, dict[str, str]] = defaultdict(dict)  # case key -> {"8d": id, ...}
        self.sqr: dict[tuple[str, int], dict] = {}
        self.fmea_rows: dict[str, list] = {}
        self.dvpr_samples: dict[tuple[str, str], int] = {}
        self._counters: Counter = Counter()

    # ------------------------------------------------------------ helpers
    def _next(self, key) -> int:
        self._counters[key] += 1
        return self._counters[key]

    def _date(self, year: int, month_lo: int = 1, month_hi: int = 12) -> str:
        return f"{year}-{self.rng.randint(month_lo, month_hi):02d}-{self.rng.randint(1, 28):02d}"

    def _people(self, n: int) -> list[str]:
        return self.rng.sample(PEOPLE, n)

    def add(self, doc: Doc) -> Doc:
        self.docs.append(doc)
        return doc

    def q(self, category: str, question: str, answer: str, facts: list[str], gold: list[list[str]], **extra):
        self.qs.append(
            {
                "category": category,
                "question": question,
                "reference_answer": answer,
                "answer_facts": facts,
                "gold": gold,
                **extra,
            }
        )

    def _case_meta(self, c: Case) -> dict:
        p = PROJECT[c.project]
        return dict(
            product_line=COMPONENTS[p.comp][0],
            component=p.comp,
            project=p.code,
            plant=c.plant,
            suppliers=[SUPPLIERS[c.supplier][0]] if c.supplier else [],
            part_numbers=[c.part],
        )

    # ------------------------------------------------------------ build
    def build(self):
        cases = sorted(CASES, key=lambda c: (c.year, c.comp, c.key))
        for c in cases:
            yy = str(c.year)[2:]
            self.ids[c.key]["8d"] = f"8D-{c.comp}-{yy}-{self._next(('8d', c.year)):03d}"
            self.ids[c.key]["ll"] = f"LL-{c.comp}-{yy}-{self._next(('ll', c.year)):03d}"
            self.ids[c.key]["tr"] = f"TR-{c.comp}-{yy}-{self._next(('tr', c.year)):03d}"
            if c.ffa:
                self.ids[c.key]["ffa"] = f"FFA-{c.comp}-{yy}-{self._next(('ffa', c.year)):03d}"
            if c.ecn:
                self.ids[c.key]["ecn"] = f"ECN-{c.year}-{self._next(('ecn', c.year)):03d}"
        self._plan_sqr()
        for i, c in enumerate(cases):
            self._8d(c, "docx" if i % 4 == 3 else "pdf")
            self._ll(c, ["md", "pdf", "docx"][i % 3])
            self._tr(c)
            if c.ffa:
                self._ffa(c)
            if c.ecn:
                self._ecn_for_case(c)
        for comp in COMPONENTS:
            self._dfmea(comp)
        for plant in PLANTS:
            self._pfmea(plant)
        for p in PROJECTS:
            self._dvpr(p)
            self._dr(p, 3)
            if p.sop >= 2022:
                self._dr(p, 2)
        for (sup, year), info in sorted(self.sqr.items()):
            self._sqr_doc(sup, year, info)
        self._work_instructions()
        self._drawings()
        self._inspections()
        self._golden(cases)
        return self

    # ------------------------------------------------------------ 8D
    def _8d(self, c: Case, fmt: str):
        p = PROJECT[c.project]
        ids = self.ids[c.key]
        opened = self._date(c.year, 1, 7)
        closed = self._date(c.year, 8, 12)
        team = self._people(5)
        sup = SUPPLIERS[c.supplier][0] if c.supplier else "Internal (Norvane)"
        so, oo, do = c.sod_before
        sn, on, dn = c.sod_after
        d5 = c.corrective + (f" The design change was released with {ids['ecn']}." if "ecn" in ids else "")
        self.add(
            Doc(
                id=ids["8d"],
                title=c.title,
                doc_type="8d",
                fmt=fmt,
                year=c.year,
                date=closed,
                author=team[0],
                **self._case_meta(c),
                blocks=[
                    (
                        "kv",
                        [
                            ("Customer", p.oem),
                            ("Project", f"{p.code} - {p.name}"),
                            ("Part number", c.part),
                            ("Part name", c.part_name),
                            ("Plant", PLANTS[c.plant]),
                            ("Supplier", sup),
                            ("Opened", opened),
                            ("Closed", closed),
                            ("8D champion", team[0]),
                        ],
                    ),
                    ("h", 1, "D1 - Team"),
                    ("list", [f"{n} - {r}" for n, r in zip(team, ROLES_8D, strict=True)]),
                    ("h", 1, "D2 - Problem description"),
                    ("p", c.symptom),
                    ("h", 1, "D3 - Interim containment action"),
                    ("p", c.containment),
                    ("h", 1, "D4 - Root cause"),
                    ("p", c.root_cause),
                    ("h", 2, "Detection"),
                    ("p", c.detection),
                    ("h", 1, "D5 - Permanent corrective action"),
                    ("p", d5),
                    ("h", 1, "D6 - Implementation and verification"),
                    ("p", f"{c.verification} Evidence: test report {ids['tr']}."),
                    ("h", 1, "D7 - Prevent recurrence"),
                    ("p", c.lesson),
                    (
                        "p",
                        f"DFMEA-{c.comp} updated for failure mode '{c.failure_mode}': severity {so}, occurrence {oo} -> {on}, "
                        f"detection {do} -> {dn}. Lessons learned published as {ids['ll']}.",
                    ),
                    ("h", 1, "D8 - Closure"),
                    (
                        "p",
                        f"8D closed on {closed} after successful verification; the {PLANTS[c.plant]} quality manager "
                        f"recognised the team.",
                    ),
                ],
            )
        )

    # ------------------------------------------------------------ lessons learned
    def _ll(self, c: Case, fmt: str):
        p = PROJECT[c.project]
        ids = self.ids[c.key]
        line, comp_name = COMPONENTS[c.comp]
        siblings = [q.code for q in PROJECTS if q.comp == c.comp and q.code != p.code]
        same_line = [COMPONENTS[k][1] for k, v in COMPONENTS.items() if v[0] == line and k != c.comp]
        applies = siblings + [f"all {n} projects" for n in same_line]
        if c.supplier:
            applies.append(f"all parts sourced from {SUPPLIERS[c.supplier][0]}")
        refs = (
            [f"8D report {ids['8d']}", f"Test report {ids['tr']}"]
            + ([f"Engineering change {ids['ecn']}"] if "ecn" in ids else [])
            + ([f"Field failure analysis {ids['ffa']}"] if "ffa" in ids else [])
        )
        self.add(
            Doc(
                id=ids["ll"],
                title=f"Lesson learned: {c.title}",
                doc_type="lessons_learned",
                fmt=fmt,
                year=c.year,
                date=self._date(c.year, 9, 12),
                author=self._people(1)[0],
                classification="public",
                **self._case_meta(c),
                blocks=[
                    ("h", 1, "Summary"),
                    (
                        "p",
                        f"{c.short.capitalize()} on {p.name} ({p.code}) for {p.oem}, {c.year}, "
                        f"{PLANTS[c.plant]}.",
                    ),
                    ("h", 1, "What happened"),
                    ("p", c.symptom),
                    ("h", 1, "Why it happened"),
                    ("p", c.root_cause),
                    ("h", 1, "What we changed"),
                    ("p", c.corrective),
                    ("h", 1, "Lesson learned"),
                    ("p", c.lesson),
                    ("h", 1, "Yokoten - horizontal deployment"),
                    ("p", "Review the following products and processes for the same risk:"),
                    ("list", applies or ["No other products currently affected."]),
                    ("h", 1, "References"),
                    ("list", refs),
                ],
            )
        )

    # ------------------------------------------------------------ test reports
    def _tr(self, c: Case):
        t, ids, p = c.test, self.ids[c.key], PROJECT[c.project]
        unit = t.get("unit", "cycles")
        lab = f"Norvane validation lab, {PLANTS[c.plant]}"
        revs = (
            [("A", t["cycles"] // 2, True), ("B", t["cycles"], False)]
            if c.key in INTERIM_TR
            else [("A", t["cycles"], False)]
        )
        for rev, done, interim in revs:
            rows, series = [], []
            for s in range(1, t["samples"] + 1):
                drift = [0.0]
                steps = 8
                for _ in range(steps):
                    drift.append(drift[-1] + abs(self.rng.gauss(0.35, 0.25)))
                series.append(drift)
                completed = f"{done:,} {unit}" if t["cycles"] > 1 else "complete"
                rows.append([f"S{s:02d}", completed, "in test" if interim else "pass", f"{drift[-1]:.1f} %"])
            limit = 10.0

            def draw(ax, series=series, done=done, limit=limit):
                xs = np.linspace(0, done, len(series[0]))
                for sr in series[:12]:
                    ax.plot(xs, sr, lw=1)
                ax.axhline(limit, color="red", ls="--", lw=1, label="limit 10 %")
                ax.set_xlabel(f"Test duration ({unit})")
                ax.set_ylabel("Parameter change (%)")
                ax.legend(loc="upper left", fontsize=7)

            status = (
                f"Interim report: {done:,} of {t['cycles']:,} {unit} completed; no failures so far. "
                f"Final report to follow."
                if interim
                else f"{t['samples'] - t['failed']} of {t['samples']} samples passed {t['requirement']}. {c.verification}"
            )
            doc = Doc(
                id=ids["tr"],
                title=f"{t['type']} test - verification of {ids['8d']}",
                doc_type="test_report",
                fmt="pdf",
                year=c.year,
                date=self._date(c.year, 6 if not interim else 3, 11 if not interim else 5),
                revision=rev,
                author=self._people(1)[0],
                **self._case_meta(c),
                supersedes=f"{ids['tr']} Rev A" if rev == "B" else None,
                superseded_by=f"{ids['tr']} Rev B" if interim else None,
                blocks=[
                    (
                        "kv",
                        [
                            ("Test", t["type"]),
                            ("Standard", t["standard"]),
                            ("Condition", t["condition"]),
                            ("Acceptance criterion", t["requirement"]),
                            ("Samples", str(t["samples"])),
                            ("Related 8D", ids["8d"]),
                            ("Project", f"{p.code} ({p.oem})"),
                            ("Laboratory", lab),
                            ("Status", "INTERIM" if interim else "FINAL"),
                        ],
                    ),
                    ("h", 1, "Purpose"),
                    (
                        "p",
                        f"Verify the permanent corrective action of {ids['8d']} ({c.title.lower()}) on the "
                        f"{c.part_name} ({c.part}).",
                    ),
                    ("h", 1, "Results"),
                    (
                        "table",
                        ["Sample", "Completed", "Result", "Parameter change"],
                        rows,
                        "Table 1: Results per sample (parameter change relative to initial measurement).",
                    ),
                    (
                        "figure",
                        lambda draw=draw: figure_png(draw),
                        f"Figure 1: Parameter change over test duration, {t['type'].lower()} "
                        f"test of the {c.part_name}.",
                    ),
                    ("h", 1, "Conclusion"),
                    ("p", status),
                ],
            )
            self.add(doc)

    # ------------------------------------------------------------ field failure analysis
    def _ffa(self, c: Case):
        ids, p = self.ids[c.key], PROJECT[c.project]
        n = FFA_RETURNS[c.key]
        beta_true = self.rng.uniform(1.6, 3.2)
        eta_true = self.rng.uniform(40_000, 120_000)
        rs = np.random.default_rng(self.rng.randrange(2**31))
        km = np.sort(eta_true * rs.weibull(beta_true, n))
        ranks = (np.arange(1, n + 1) - 0.3) / (n + 0.4)  # Bernard's median ranks
        x, y = np.log(km), np.log(-np.log(1 - ranks))
        beta, intercept = np.polyfit(x, y, 1)
        eta = math.exp(-intercept / beta)
        months = [f"{c.year}-{m:02d}" for m in range(1, 13)]
        per_month = np.bincount(np.minimum((km / km.max() * 11.999).astype(int), 11), minlength=12)
        cum = np.cumsum(per_month)
        rows = [[m, int(a), int(b)] for m, a, b in zip(months, per_month, cum, strict=True)]
        self.ids[c.key]["ffa_beta"] = f"{beta:.2f}"
        self.ids[c.key]["ffa_eta"] = f"{eta:,.0f}"

        def bars(ax):
            ax.bar(range(12), per_month, color="#3b6ea5")
            ax.set_xticks(range(12), [m[5:] for m in months])
            ax.set_xlabel(f"Month of {c.year}")
            ax.set_ylabel("Returns")

        def weib(ax):
            ax.scatter(x, y, s=10)
            xs = np.linspace(x.min(), x.max(), 50)
            ax.plot(xs, beta * xs + intercept, color="red", lw=1)
            ax.set_xlabel("ln(mileage km)")
            ax.set_ylabel("ln(-ln(1-F))")

        restricted = p.oem == "Kairo EV"
        self.add(
            Doc(
                id=ids["ffa"],
                title=f"Field failure analysis: {c.short}",
                doc_type="field_failure",
                fmt="pdf",
                year=c.year,
                date=self._date(c.year, 6, 10),
                author=self._people(1)[0],
                classification="restricted" if restricted else "confidential",
                **self._case_meta(c),
                blocks=[
                    (
                        "kv",
                        [
                            ("Customer", p.oem),
                            ("Project", p.code),
                            ("Part", f"{c.part} {c.part_name}"),
                            ("Returns analysed", str(n)),
                            ("Related 8D", ids["8d"]),
                        ],
                    ),
                    ("h", 1, "Field return data"),
                    ("table", ["Month", "Returns", "Cumulative"], rows, "Table 1: Field returns by month."),
                    (
                        "figure",
                        lambda: figure_png(bars),
                        f"Figure 1: Monthly field returns of the {c.part_name}.",
                    ),
                    ("h", 1, "Weibull analysis"),
                    (
                        "p",
                        f"Time-to-failure data for {n} returns (vehicle mileage in km) was fitted by median-rank "
                        f"regression. Shape parameter beta = {beta:.2f}, characteristic life eta = {eta:,.0f} km. "
                        f"{'beta above 1 indicates a wear-out failure mechanism.' if beta > 1 else ''}",
                    ),
                    (
                        "figure",
                        lambda: figure_png(weib),
                        "Figure 2: Weibull probability plot with regression line.",
                    ),
                    ("h", 1, "Failure analysis findings"),
                    ("p", c.root_cause),
                    ("p", c.detection),
                    ("h", 1, "Conclusion"),
                    ("p", f"Root cause confirmed; corrective actions tracked in {ids['8d']}."),
                ],
            )
        )

    # ------------------------------------------------------------ ECN
    def _ecn_doc(self, ecn_id, year, part, part_name, meta, what, frm, to, reason, affected, validation):
        self.add(
            Doc(
                id=ecn_id,
                title=f"Engineering change: {what}",
                doc_type="ecn",
                fmt="md",
                year=year,
                date=self._date(year, 5, 11),
                author=self._people(1)[0],
                **meta,
                blocks=[
                    (
                        "kv",
                        [
                            ("Change request", ecn_id.replace("ECN", "ECR")),
                            ("Part number", part),
                            ("Part name", part_name),
                            ("Change type", "Design / material / process"),
                            ("Approved by", ", ".join(self._people(2))),
                        ],
                    ),
                    ("h", 1, "Description of change"),
                    ("table", ["Item", "From", "To"], [[what, frm, to]], None),
                    ("h", 1, "Reason for change"),
                    ("p", reason),
                    ("h", 1, "Affected documents"),
                    ("list", affected),
                    ("h", 1, "Validation"),
                    ("p", validation),
                ],
            )
        )

    def _ecn_for_case(self, c: Case):
        ids = self.ids[c.key]
        self._ecn_doc(
            ids["ecn"],
            c.year,
            c.part,
            c.part_name,
            self._case_meta(c),
            c.ecn["what"],
            c.ecn["from"],
            c.ecn["to"],
            f"Permanent corrective action for {ids['8d']} ({c.title.lower()}). {c.root_cause.split('. ')[0]}.",
            [f"Drawing {c.part}", f"DFMEA-{c.comp}", f"Control plan {PLANTS[c.plant]}"],
            f"Validated by test report {ids['tr']}.",
        )

    # ------------------------------------------------------------ DFMEA / PFMEA
    def _dfmea_rows(self, comp: str, upto_year: int):
        rows = []
        for c in sorted((c for c in CASES if c.comp == comp and c.year <= upto_year), key=lambda c: c.year):
            s, o, d = c.sod_before
            closed = not (comp == "INV" and upto_year == 2022 and c.year == 2022)  # Rev C predates the fix
            sa, oa, da = c.sod_after
            rows.append(
                [
                    c.part_name,
                    c.failure_mode,
                    c.effect,
                    s,
                    c.cause,
                    "Design guideline / lessons learned review",
                    f"{c.test['type']} ({c.test['standard']})",
                    o,
                    d,
                    action_priority(s, o, d),
                    c.corrective,
                    self.rng.choice(PEOPLE),
                    f"{c.year}-12-15",
                    "Closed" if closed else "In progress",
                    oa if closed else "",
                    da if closed else "",
                    action_priority(sa, oa, da) if closed else "",
                ]
            )
        for fm, eff, cause, s, o, d in EXTRA_FMEA[comp]:
            ap = action_priority(s, o, d)
            rows.append(
                [
                    COMPONENTS[comp][1],
                    fm,
                    eff,
                    s,
                    cause,
                    "Design standard",
                    "DV test",
                    o,
                    d,
                    ap,
                    "Review in next design loop" if ap != "L" else "None - controls adequate",
                    self.rng.choice(PEOPLE),
                    "",
                    "Open" if ap != "L" else "n/a",
                    "",
                    "",
                    "",
                ]
            )
        return [[f"{comp}-FM-{i + 1:02d}", *r] for i, r in enumerate(rows)]

    FMEA_HEADER = [
        "ID",
        "Item / Function",
        "Failure mode",
        "Effect",
        "S",
        "Cause",
        "Prevention control",
        "Detection control",
        "O",
        "D",
        "AP",
        "Recommended action",
        "Responsible",
        "Target date",
        "Status",
        "Revised O",
        "Revised D",
        "Revised AP",
    ]

    def _dfmea(self, comp: str):
        line, name = COMPONENTS[comp]
        years = [c.year for c in CASES if c.comp == comp]
        revs = (
            [("C", 2022, 2022, "D"), ("D", 2024, 2024, None)]
            if comp == "INV"
            else [("B", max(years), max(years), None)]
        )
        for rev, year, upto, next_rev in revs:
            rows = self._dfmea_rows(comp, upto)
            if not next_rev:
                self.fmea_rows[comp] = rows
            self.add(
                Doc(
                    id=f"DFMEA-{comp}",
                    title=f"Design FMEA - {name}",
                    doc_type="dfmea",
                    fmt="xlsx",
                    year=year,
                    date=self._date(year, 10, 12),
                    revision=rev,
                    author=self._people(1)[0],
                    product_line=line,
                    component=comp,
                    supersedes=f"DFMEA-{comp} Rev C" if rev == "D" else None,
                    superseded_by=f"DFMEA-{comp} Rev {next_rev}" if next_rev else None,
                    part_numbers=sorted({c.part for c in CASES if c.comp == comp}),
                    sheets=[("DFMEA", self.FMEA_HEADER, rows)],
                )
            )

    def _pfmea(self, plant: str):
        rows = []
        for key, step in PROCESS_STEP.items():
            c = next(c for c in CASES if c.key == key)
            if c.plant != plant:
                continue
            s, o, d = c.sod_before
            sa, oa, da = c.sod_after
            rows.append(
                [
                    step,
                    c.failure_mode,
                    c.effect,
                    s,
                    c.cause,
                    o,
                    d,
                    action_priority(s, o, d),
                    c.corrective,
                    "Closed",
                    oa,
                    da,
                    action_priority(sa, oa, da),
                ]
            )
        for step, fm, eff, s, cause, o, d in [
            ("Screw fastening", "Under-torque", "Loose joint", 7, "Tool calibration drift", 3, 3),
            ("End-of-line test", "Test escape", "Defect shipped", 8, "Test limit set wrong", 2, 4),
            ("Labelling", "Wrong label", "Traceability loss", 5, "Manual label selection", 3, 5),
        ]:
            ap = action_priority(s, o, d)
            rows.append(
                [step, fm, eff, s, cause, o, d, ap, "Monitor" if ap != "L" else "None", "Open", "", "", ""]
            )
        rows = [[f"{plant}-PF-{i + 1:02d}", *r] for i, r in enumerate(rows)]
        self.add(
            Doc(
                id=f"PFMEA-{plant}",
                title=f"Process FMEA - {PLANTS[plant]}",
                doc_type="pfmea",
                fmt="xlsx",
                year=2024,
                date=self._date(2024, 1, 6),
                revision="B",
                author=self._people(1)[0],
                plant=plant,
                sheets=[
                    (
                        "PFMEA",
                        [
                            "ID",
                            "Process step",
                            "Failure mode",
                            "Effect",
                            "S",
                            "Cause",
                            "O",
                            "D",
                            "AP",
                            "Recommended action",
                            "Status",
                            "Revised O",
                            "Revised D",
                            "Revised AP",
                        ],
                        rows,
                    )
                ],
            )
        )

    # ------------------------------------------------------------ DVP&R
    def _dvpr(self, p):
        line = COMPONENTS[p.comp][0]
        rows = []
        for i, (name, std, cond, acc) in enumerate(GENERIC_TESTS[line]):
            n = self.rng.choice([3, 6, 6, 10, 12])
            self.dvpr_samples[(p.code, name)] = n
            rows.append(
                [
                    f"{p.code}-T{i + 1:02d}",
                    name,
                    std,
                    cond,
                    acc,
                    n,
                    "DV",
                    f"{p.sop - 1}-{3 + i:02d}",
                    "Passed",
                    f"Lab log {p.code[2:]}-{i + 1:02d}",
                ]
            )
        for c in CASES:
            if c.project == p.code:
                t = c.test
                rows.append(
                    [
                        f"{p.code}-T{len(rows) + 1:02d}",
                        t["type"],
                        t["standard"],
                        t["condition"],
                        t["requirement"],
                        t["samples"],
                        "PV (corrective action)",
                        f"{c.year}-10",
                        "Passed",
                        self.ids[c.key]["tr"],
                    ]
                )
        self.add(
            Doc(
                id=f"DVP-{p.code}",
                title=f"DVP&R - {p.name}",
                doc_type="dvpr",
                fmt="xlsx",
                year=max(p.sop, 2021),
                date=self._date(p.sop, 1, 4),
                author=self._people(1)[0],
                product_line=line,
                component=p.comp,
                project=p.code,
                plant=p.plant,
                sheets=[
                    (
                        "DVP&R",
                        [
                            "Test ID",
                            "Test",
                            "Standard",
                            "Condition",
                            "Acceptance",
                            "Samples",
                            "Phase",
                            "Planned",
                            "Status",
                            "Report",
                        ],
                        rows,
                    )
                ],
            )
        )

    # ------------------------------------------------------------ design review minutes
    def _dr(self, p, gate: int):
        year = p.sop - 1 if gate == 2 else p.sop
        date = self._date(year, 2, 9)
        people = self._people(5)
        sups = sorted({c.supplier for c in CASES if c.project == p.code and c.supplier})
        if p.code == "P-RAD-2204":
            sups = ["VLX"]
        decisions = [
            f"Gate DR{gate} passed{' with conditions' if gate == 2 else ''}.",
            f"SOP confirmed for {p.sop} at {PLANTS[p.plant]}.",
        ]
        for s in sups:
            decisions.append(
                f"{SUPPLIERS[s][0]} approved as supplier for {SUPPLIERS[s][1]} "
                f"(process audit score {self.rng.randint(82, 91)}%)."
            )
        risks = [
            f"{c.title} - tracked in {self.ids[c.key]['8d']}"
            for c in CASES
            if c.project == p.code and c.year <= year
        ]
        actions = [
            ["1", "Complete DV test report package", people[1], f"{year}-12-15"],
            ["2", "Update DFMEA with DV findings", people[2], f"{year}-11-30"],
            ["3", "Submit PPAP to customer", people[3], f"{p.sop}-03-31"],
        ]
        self.add(
            Doc(
                id=f"DR-{p.code}-G{gate}",
                title=f"Design review DR{gate} - {p.name}",
                doc_type="design_review",
                fmt="docx",
                year=year,
                date=date,
                author=people[0],
                product_line=COMPONENTS[p.comp][0],
                component=p.comp,
                project=p.code,
                plant=p.plant,
                suppliers=[SUPPLIERS[s][0] for s in sups],
                blocks=[
                    (
                        "kv",
                        [
                            ("Project", f"{p.code} - {p.name}"),
                            ("Customer", p.oem),
                            ("Gate", f"DR{gate}"),
                            ("Date", date),
                            ("Chair", people[0]),
                        ],
                    ),
                    ("h", 1, "Attendees"),
                    (
                        "list",
                        [
                            f"{n} ({r})"
                            for n, r in zip(
                                people,
                                ["Chair, chief engineer", "Validation", "Design", "Quality", "Purchasing"],
                                strict=True,
                            )
                        ],
                    ),
                    ("h", 1, "Status summary"),
                    (
                        "p",
                        f"{p.name} for {p.oem}; SOP {p.sop}. DV testing {self.rng.randint(70, 100)}% complete, "
                        f"PV testing {self.rng.randint(0, 60) if gate == 2 else 100}% complete.",
                    ),
                    ("h", 1, "Decisions"),
                    ("list", decisions),
                    ("h", 1, "Risks and open issues"),
                    ("list", risks or ["No open quality issues."]),
                    ("h", 1, "Action items"),
                    ("table", ["#", "Action", "Owner", "Due"], actions, None),
                ],
            )
        )

    # ------------------------------------------------------------ supplier quality
    def _plan_sqr(self):
        for sup in SUPPLIERS:
            prev_issue = None
            for year in SQR_YEARS:
                issues = [c for c in CASES if c.supplier == sup and c.year == year]
                base = self.rng.randint(15, 70)
                if issues:
                    ppm = base * self.rng.randint(5, 9)
                    status = (
                        "New Business Hold" if max(c.sod_before[0] for c in issues) >= 8 else "Conditional"
                    )
                elif prev_issue and prev_issue == year - 1:
                    ppm, status = base * 2, "Conditional"
                else:
                    ppm, status = base, "Approved"
                if issues:
                    prev_issue = year
                self.sqr[(sup, year)] = {
                    "ppm": ppm,
                    "status": status,
                    "issues": issues,
                    "all_issues": [c for c in CASES if c.supplier == sup and c.year <= year],
                    "audit": self.rng.randint(68, 79) if issues else self.rng.randint(80, 94),
                }

    def _sqr_doc(self, sup: str, year: int, info: dict):
        name, commodity = SUPPLIERS[sup]
        delivered = [self.rng.randint(80_000, 240_000) for _ in range(4)]
        total = sum(delivered)
        rejects_total = round(info["ppm"] * total / 1e6)
        rejects = [
            int(r)
            for r in np.random.default_rng(self.rng.randrange(2**31)).multinomial(rejects_total, [0.25] * 4)
        ]
        ppm = round(sum(rejects) / total * 1e6)
        info["ppm"] = ppm
        rows = [
            [
                f"Q{i + 1}",
                f"{delivered[i]:,}",
                rejects[i],
                round(rejects[i] / delivered[i] * 1e6),
                f"{self.rng.uniform(94, 99.8):.1f}%",
            ]
            for i in range(4)
        ]
        rows.append(["Year", f"{total:,}", sum(rejects), ppm, ""])
        eightds = [
            f"{self.ids[c.key]['8d']} - {c.title} ({'opened' if c.year == year else 'closed'} {c.year})"
            for c in info["all_issues"]
        ]
        reason = {
            "New Business Hold": "Placed on New Business Hold: no new sourcing awards until the 8D actions are verified "
            "and a re-audit scores at least 80%.",
            "Conditional": "Conditional approval: supplier under enhanced monitoring with monthly quality reviews.",
            "Approved": "Approved supplier; no restrictions for new business.",
        }[info["status"]]
        self.add(
            Doc(
                id=f"SQR-{sup}-{year}",
                title=f"Supplier quality report {year} - {name}",
                doc_type="supplier_quality",
                fmt="pdf",
                year=year,
                date=f"{year + 1}-01-{self.rng.randint(10, 28):02d}",
                author=self._people(1)[0],
                classification="confidential",
                suppliers=[name],
                blocks=[
                    (
                        "kv",
                        [
                            ("Supplier", name),
                            ("Supplier code", sup),
                            ("Commodity", commodity),
                            ("Year", str(year)),
                            ("Status", info["status"]),
                        ],
                    ),
                    ("h", 1, "KPI summary"),
                    (
                        "table",
                        ["Quarter", "Delivered parts", "Rejected parts", "PPM", "On-time delivery"],
                        rows,
                        f"Table 1: Quality and delivery KPIs {year}. Annual PPM {ppm}.",
                    ),
                    ("h", 1, "Process audit"),
                    (
                        "p",
                        f"VDA 6.3 process audit score {info['audit']}% "
                        f"({'A' if info['audit'] >= 90 else 'B' if info['audit'] >= 80 else 'C'} rating).",
                    ),
                    ("h", 1, "8D reports"),
                    ("list", eightds or ["No 8D reports raised."]),
                    ("h", 1, "Status and decision"),
                    ("p", reason),
                ],
            )
        )

    # ------------------------------------------------------------ work instructions
    def _wi_doc(
        self,
        wid,
        plant,
        comp,
        title,
        rev,
        year,
        spec,
        supersedes=None,
        superseded_by=None,
        history=None,
        steps=None,
    ):
        steps = steps or [
            [
                "1",
                f"Verify part numbers against the traveller for the {COMPONENTS[comp][1]}.",
                "Scan both labels",
            ],
            ["2", f"Perform the operation: {title.lower()}.", f"Specification: {spec}"],
            ["3", "Record the result in the MES.", "No manual edits"],
            ["4", "Place the part in the outgoing tray.", "Max 20 parts per tray"],
        ]
        blocks = [
            ("kv", [("Plant", PLANTS[plant]), ("Product", COMPONENTS[comp][1]), ("Revision", rev)]),
            ("h", 1, "Safety"),
            ("list", ["Safety glasses", "ESD wrist strap where marked", "Cut-resistant gloves"]),
            ("h", 1, "Steps"),
            ("table", ["Step", "Description", "Key point"], steps, None),
            ("h", 1, "Specification"),
            ("table", ["Parameter", "Value"], [[title, spec]], None),
        ]
        if history:
            blocks += [
                ("h", 1, "Change history"),
                ("table", ["Revision", "Change", "Reference"], history, None),
            ]
        self.add(
            Doc(
                id=wid,
                title=f"Work instruction: {title}",
                doc_type="work_instruction",
                fmt="docx",
                year=year,
                date=self._date(year, 2, 10),
                revision=rev,
                author=self._people(1)[0],
                product_line=COMPONENTS[comp][0],
                component=comp,
                plant=plant,
                supersedes=supersedes,
                superseded_by=superseded_by,
                blocks=blocks,
            )
        )

    def _work_instructions(self):
        self.wi_ecn = {}
        for wid, plant, comp, title, spec_a, spec_b, reason in WORK_INSTRUCTIONS:
            year_b = max(c.year for c in CASES if c.comp == comp) + (1 if comp != "INV" else 0)
            year_b = min(year_b, 2024)
            ecn_id = f"ECN-{year_b}-{self._next(('ecn', year_b)):03d}"
            self.wi_ecn[wid] = ecn_id
            self._wi_doc(wid, plant, comp, title, "A", 2021, spec_a, superseded_by=f"{wid} Rev B")
            self._wi_doc(
                wid,
                plant,
                comp,
                title,
                "B",
                year_b,
                spec_b,
                supersedes=f"{wid} Rev A",
                history=[
                    ["A", "Initial release", "-"],
                    ["B", f"{title}: {spec_a} changed to {spec_b}", ecn_id],
                ],
            )
            self._ecn_doc(
                ecn_id,
                year_b,
                "-",
                title,
                dict(product_line=COMPONENTS[comp][0], component=comp, plant=plant),
                f"{title} specification",
                spec_a,
                spec_b,
                reason,
                [f"{wid} Rev B", f"PFMEA-{plant}"],
                "Validated by process capability study (Cpk above 1.67).",
            )
        for wid, plant, comp, title, spec in [
            ("WI-CHN-003", "CHN", "RAD", "Brazing furnace set-up", "belt speed 0.9 m/min, locked recipe"),
            (
                "WI-TLC-015",
                "TLC",
                "INJ",
                "Coil winding machine maintenance",
                "replace wire guide every 500,000 cycles",
            ),
            (
                "WI-PN2-008",
                "PN2",
                "SNS",
                "MAP sensor connector seal assembly",
                "automatic silicone-free lubricant, press blocked without lubricant detection",
            ),
            (
                "WI-KRK-004",
                "KRK",
                "EPS",
                "Rotor magnet bonding",
                "hardened locators checked every shift; skew 7.5 degrees",
            ),
        ]:
            self._wi_doc(wid, plant, comp, title, "A", 2024, spec)

    # ------------------------------------------------------------ scanned drawings & inspection records
    def _drawings(self):
        for comp, part, title, material, finish, rev, scale, note in DRAWINGS:
            year = self.rng.randint(2021, 2024)
            dims = (
                f"{self.rng.randint(180, 420)}",
                f"{self.rng.randint(90, 240)}",
                f"{self.rng.randint(20, 60)}",
            )
            self.add(
                Doc(
                    id=f"DWG-{part}",
                    title=f"Drawing {part} {title}",
                    doc_type="drawing",
                    fmt="png",
                    year=year,
                    date=self._date(year),
                    revision=rev,
                    component=comp,
                    product_line=COMPONENTS[comp][0],
                    part_numbers=[part],
                    scan={
                        "kind": "drawing",
                        "part": part,
                        "title": title,
                        "material": material,
                        "finish": finish,
                        "rev": rev,
                        "scale": scale,
                        "drawn": self._people(1)[0].upper(),
                        "date": self._date(year),
                        "dim_w": f"{dims[0]} +/-0.5",
                        "dim_h": f"{dims[1]} +/-0.5",
                        "dim_bore": f"D{dims[2]} H7",
                        "notes": [
                            "ALL DIMENSIONS IN MM",
                            "GENERAL TOLERANCES ISO 2768-M",
                            note,
                            "REMOVE ALL SHARP EDGES",
                        ],
                        "skew": round(self.rng.uniform(1.5, 4.5), 1),
                    },
                )
            )

    def _inspections(self):
        for plant, sup, part, part_name, lot, year, rows, decision in INSPECTIONS:
            iid = f"IR-{plant}-{str(year)[2:]}-{self._next(('ir', plant, year)):03d}"
            self.add(
                Doc(
                    id=iid,
                    title=f"Incoming inspection {lot}",
                    doc_type="inspection_record",
                    fmt="jpg",
                    year=year,
                    date=self._date(year),
                    plant=plant,
                    suppliers=[SUPPLIERS[sup][0]],
                    part_numbers=[part],
                    component=part.split("-")[0],
                    product_line=COMPONENTS[part.split("-")[0]][0],
                    scan={
                        "kind": "inspection",
                        "rows": rows,
                        "decision": decision,
                        "inspector": self._people(1)[0],
                        "remarks": "Lot blocked, supplier informed"
                        if decision == "REJECT"
                        else "Released to stock",
                        "header": [
                            ("Supplier", SUPPLIERS[sup][0]),
                            ("Part", f"{part} {part_name}"),
                            ("Lot", lot),
                            ("Date", self._date(year)),
                            ("Plant", PLANTS[plant]),
                        ],
                        "skew": round(self.rng.uniform(1.5, 5.0), 1),
                    },
                )
            )
            self.ids[lot] = {"ir": iid}

    # ------------------------------------------------------------ golden set
    def _golden(self, cases: list[Case]):
        rng = random.Random(7)
        by_key = {c.key: c for c in cases}

        def docs_for(c, *kinds):
            return [self.ids[c.key][k] for k in kinds if k in self.ids[c.key]]

        # factual: root cause / containment / corrective
        pick = rng.sample(cases, 26)
        for c in pick[:14]:
            self.q(
                "factual",
                f"What was the root cause of the {c.short} on project {c.project}?",
                c.root_cause,
                c.rc_keys,
                [docs_for(c, "8d", "ll", "ffa")],
                evidence=c.rc_keys[0],
            )
        for c in pick[14:22]:
            self.q(
                "factual",
                f"What permanent corrective action was implemented for the {c.short}?",
                c.corrective,
                c.ca_keys,
                [docs_for(c, "8d", "ll", "ecn")],
                evidence=c.ca_keys[0],
            )
        for c in pick[22:26]:
            self.q(
                "factual",
                f"How was the {c.short} contained before the permanent fix?",
                c.containment,
                c.cont_keys,
                [docs_for(c, "8d")],
                evidence=c.cont_keys[0],
            )
        # numeric facts stated in the 8D text
        for c in rng.sample(cases, 12):
            self.q(
                "numeric",
                c.num_q,
                c.num_a,
                num_facts(c.num_a),
                [docs_for(c, "8d", "ll", "ffa")],
                evidence=c.num_a,
            )
        # table lookups: DFMEA, SQR, DVP&R, FFA
        for comp in rng.sample(list(EXTRA_FMEA), 3):
            fm, _, _, s, o, d = EXTRA_FMEA[comp][0]
            ap = action_priority(s, o, d)
            self.q(
                "table",
                f"What severity, occurrence and detection ratings does the {COMPONENTS[comp][1]} DFMEA give "
                f"the failure mode '{fm}', and what is its action priority?",
                f"S={s}, O={o}, D={d}, action priority {ap}.",
                [str(s), str(o), str(d), AP_WORD[ap]],
                [[f"DFMEA-{comp}"]],
                evidence=fm,
            )
        for sup, year in rng.sample(sorted(self.sqr), 3):
            info = self.sqr[(sup, year)]
            self.q(
                "table",
                f"What was the annual PPM of {SUPPLIERS[sup][0]} in {year}?",
                f"{info['ppm']} PPM",
                [str(info["ppm"])],
                [[f"SQR-{sup}-{year}"]],
                evidence=str(info["ppm"]),
            )
        for (code, test), n in rng.sample(sorted(self.dvpr_samples.items()), 2):
            self.q(
                "table",
                f"How many samples are planned for the {test.lower()} test in the DVP&R of project {code}?",
                str(n),
                [str(n)],
                [[f"DVP-{code}"]],
                evidence=test,
            )
        for key in ["inv-solder-fatigue", "wpm-gear-wear"]:
            c = by_key[key]
            self.q(
                "table",
                f"What Weibull shape parameter (beta) was estimated in the field failure analysis of the "
                f"{c.short}?",
                self.ids[key]["ffa_beta"],
                [self.ids[key]["ffa_beta"]],
                [[self.ids[key]["ffa"]]],
                evidence=self.ids[key]["ffa_beta"],
            )
        # multi-hop
        sup_cases = [c for c in cases if c.supplier and c.year in SQR_YEARS]
        for c in rng.sample(sup_cases, 5):
            info = self.sqr[(c.supplier, c.year)]
            self.q(
                "multi_hop",
                f"What was the annual PPM in {c.year} of the supplier involved in the {c.short}?",
                f"{SUPPLIERS[c.supplier][0]}: {info['ppm']} PPM in {c.year}.",
                [SUPPLIERS[c.supplier][0].split()[0], str(info["ppm"])],
                [docs_for(c, "8d", "ll"), [f"SQR-{c.supplier}-{c.year}"]],
                evidence=str(info["ppm"]),
            )
        for c in rng.sample([c for c in cases if c.ecn], 4):
            self.q(
                "multi_hop",
                f"Which engineering change notice implemented the fix for the {c.short}, and what did it "
                f"change the {c.ecn['what']} to?",
                f"{self.ids[c.key]['ecn']}: {c.ecn['to']}.",
                [self.ids[c.key]["ecn"].lower()] + num_facts(c.ecn["to"])[:2],
                [[self.ids[c.key]["ecn"]], docs_for(c, "8d", "ll")],
                evidence=c.ecn["to"],
            )
        for c in rng.sample(cases, 3):
            s, o, d = c.sod_before
            ap = action_priority(s, o, d)
            self.q(
                "multi_hop",
                f"In the DFMEA, what action priority did the failure mode behind the {c.short} have "
                f"before corrective actions?",
                f"{c.failure_mode}: S={s}, O={o}, D={d}, AP {ap}.",
                [AP_WORD[ap]],
                [[f"DFMEA-{c.comp}"], docs_for(c, "8d")],
                evidence=c.failure_mode,
            )
        for c in rng.sample(cases, 2):
            p = PROJECT[c.project]
            self.q(
                "multi_hop",
                f"Which customer was affected by the {c.short}, and what is that project's SOP year?",
                f"{p.oem}; SOP {p.sop}.",
                [p.oem.split()[0], str(p.sop)],
                [docs_for(c, "8d"), [f"DR-{p.code}-G3", f"DVP-{p.code}", f"DR-{p.code}-G2"]],
                evidence=p.oem,
            )
        # OCR-only (answers exist only in scanned images)
        for comp, part, title, material, *_ in DRAWINGS[:7]:
            self.q(
                "ocr",
                f"What material is specified on the drawing of part {part} ({title.lower()})?",
                material,
                [material.split()[0].lower()],
                [[f"DWG-{part}"]],
                evidence=material.split()[0],
            )
        for comp, part, title, material, finish, rev, *_ in DRAWINGS[7:9]:
            self.q(
                "ocr",
                f"What revision is the drawing of part {part}?",
                f"Revision {rev}",
                [f"rev {rev.lower()}|revision {rev.lower()}"],
                [[f"DWG-{part}"]],
                evidence=part,
            )
        note = DRAWINGS[9][7]
        self.q(
            "ocr",
            f"What runout tolerance is noted on the drawing of rotor shaft {DRAWINGS[9][1]}?",
            note.title(),
            ["0.02"],
            [[f"DWG-{DRAWINGS[9][1]}"]],
            evidence="0.02",
        )
        for plant, sup, part, part_name, lot, year, rows, decision in [
            INSPECTIONS[0],
            INSPECTIONS[2],
            INSPECTIONS[6],
        ]:
            iid = self.ids[lot]["ir"]
            if decision == "ACCEPT":
                char, spec, meas, _ = rows[0]
                self.q(
                    "ocr",
                    f"What {char.lower()} was measured on {SUPPLIERS[sup][0]} lot {lot} at incoming inspection?",
                    meas,
                    num_facts(meas),
                    [[iid]],
                    evidence=meas.split()[0],
                )
            else:
                bad = next(r for r in rows if r[3] == "NG")
                self.q(
                    "ocr",
                    f"Was {SUPPLIERS[sup][0]} lot {lot} accepted at incoming inspection, and why?",
                    f"Rejected: {bad[0]} measured {bad[2]} against {bad[1]}.",
                    ["reject", bad[2].split()[0].lower()],
                    [[iid]],
                    evidence=lot,
                )
        # conversational follow-ups
        follow = [
            ("What was the root cause?", "root_cause", "rc_keys"),
            ("How was it contained?", "containment", "cont_keys"),
            ("What was the permanent fix?", "corrective", "ca_keys"),
            ("What lesson did the team record?", "lesson", "lesson_keys"),
        ]
        for i, c in enumerate(rng.sample(cases, 10)):
            fq, field_, keys = follow[i % 4]
            history = [
                {"role": "user", "content": f"What happened with the {c.short} on {c.project}?"},
                {
                    "role": "assistant",
                    "content": f"{c.symptom.split('. ')[0].rstrip('.')}. It was handled in {self.ids[c.key]['8d']}.",
                },
            ]
            self.q(
                "conversational",
                fq,
                getattr(c, field_),
                getattr(c, keys),
                [docs_for(c, "8d", "ll")],
                history=history,
                evidence=getattr(c, keys)[0],
            )
        # filter-style list questions
        filt = []
        for comp, (line, name) in COMPONENTS.items():
            cs = sorted((c for c in cases if c.comp == comp), key=lambda c: c.year)
            if len(cs) >= 3:
                y = cs[0].year
                sel = [c for c in cs if c.year > y]
                filt.append((f"Which {name} lessons learned were recorded after {y}?", sel, "ll"))
        for plant in PLANTS:
            for year in (2022, 2023):
                sel = [c for c in cases if c.plant == plant and c.year == year]
                if 2 <= len(sel) <= 4:
                    filt.append(
                        (
                            f"Which 8D reports were opened at the {PLANTS[plant].split(' (')[0]} in {year}?",
                            sel,
                            "8d",
                        )
                    )
        for sup in ("SCS", "VLX", "QTC", "MWC"):
            sel = [c for c in cases if c.supplier == sup]
            filt.append((f"Which quality issues involved {SUPPLIERS[sup][0]}?", sel, "8d"))
        for text, sel, kind in rng.sample(filt, min(10, len(filt))):
            self.q(
                "filter",
                text,
                "; ".join(f"{c.title} ({self.ids[c.key][kind]})" for c in sel),
                [TAGS[c.key] for c in sel],
                [[self.ids[c.key][kind], self.ids[c.key]["8d"], self.ids[c.key]["ll"]] for c in sel],
                evidence=None,
            )
        # recency: superseded revisions and contradictions
        for wid, plant, comp, title, a, b, _ in WORK_INSTRUCTIONS:
            self.q(
                "recency",
                f"What is the current specification for {title.lower()} at the "
                f"{PLANTS[plant].split(' (')[0]}?",
                f"{b} (Rev B; Rev A specified {a}).",
                num_facts(b),
                [[wid]],
                evidence=b,
                must_prefer_revision="B",
            )
        c = by_key["inv-solder-fatigue"]
        self.q(
            "recency",
            "What is the current occurrence rating for die-attach solder fatigue in the traction inverter "
            "DFMEA?",
            f"{c.sod_after[1]} (Rev D; it was {c.sod_before[1]} in Rev C).",
            [str(c.sod_after[1])],
            [["DFMEA-INV"]],
            evidence=c.failure_mode,
            must_prefer_revision="D",
        )
        c = by_key["rad-tank-crack"]
        self.q(
            "recency",
            f"How many cycles were completed in the final test report verifying the {c.short} fix, and "
            f"how many samples failed?",
            f"{c.test['cycles']:,} cycles, 0 failures (final Rev B).",
            [str(c.test["cycles"]), "0|no|zero|none"],
            [[self.ids[c.key]["tr"]]],
            evidence=None,
            must_prefer_revision="B",
        )
        vlx = self.sqr[("VLX", max(SQR_YEARS))]
        self.q(
            "recency",
            "What is the current supplier status of Veltrix Polymers?",
            f"{vlx['status']} (latest supplier quality report {max(SQR_YEARS)}).",
            [vlx["status"].lower()],
            [[f"SQR-VLX-{max(SQR_YEARS)}"]],
            evidence=vlx["status"],
        )
        # analytical (answerable exactly by counting structured data; routed to text-to-SQL in P6)
        eights = [d for d in self.docs if d.doc_type == "8d"]
        count = Counter(d.component for d in eights)
        yr = Counter(d.year for d in eights)
        plant_top = Counter(d.plant for d in eights).most_common(1)[0]
        hi_rad = sum(1 for r in self.fmea_rows["RAD"] if r[10] == "H")
        hi_all = sum(1 for rows in self.fmea_rows.values() for r in rows if r[10] == "H")
        sup23 = sum(1 for d in eights if d.year == 2023 and d.suppliers)
        tr_el = len(
            {d.id for d in self.docs if d.doc_type == "test_report" and d.product_line == "electrification"}
        )
        ll_body = sum(
            1 for d in self.docs if d.doc_type == "lessons_learned" and d.product_line == "body_electronics"
        )
        for qtext, ans in [
            ("How many 8D reports were opened for traction inverters?", count["INV"]),
            ("How many 8D reports were opened in 2022?", yr[2022]),
            ("How many 8D reports in 2023 involved an external supplier?", sup23),
            ("How many radiator DFMEA items have High action priority?", hi_rad),
            ("How many DFMEA items across all components have High action priority?", hi_all),
            ("How many distinct test reports exist for electrification products?", tr_el),
            ("How many lessons-learned reports were published for body electronics?", ll_body),
        ]:
            self.q("analytical", qtext, str(ans), [str(ans)], [], evidence=None)
        self.q(
            "analytical",
            "Which plant has the most 8D reports?",
            f"{PLANTS[plant_top[0]]} ({plant_top[1]})",
            [PLANTS[plant_top[0]].split()[0].lower()],
            [],
            evidence=None,
        )
        # unanswerable
        for qtext in UNANSWERABLE:
            self.q(
                "unanswerable",
                qtext,
                "The knowledge base does not contain this information.",
                [],
                [],
                evidence=None,
            )

        # stable ids + stratified dev/test split
        by_cat = defaultdict(list)
        for q in self.qs:
            by_cat[q["category"]].append(q)
        for cat, qs in by_cat.items():
            order = list(range(len(qs)))
            rng.shuffle(order)
            n_dev = round(len(qs) * 0.4)
            for rank, idx in enumerate(order):
                qs[idx]["split"] = "dev" if rank < n_dev else "test"
        for i, q in enumerate(self.qs):
            q["id"] = f"Q{i + 1:03d}"
