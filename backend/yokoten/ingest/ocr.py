"""Image processing + OCR for scanned documents and drawings.

preprocess(): grayscale -> denoise -> deskew (projection-profile search) -> adaptive threshold.
ocr(): Tesseract when the binary is available, EasyOCR otherwise. Returns text lines with bbox + confidence.
"""

import os
import re
import shutil
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

import cv2
import numpy as np

from yokoten.config import device, settings

TESSERACT_PATHS = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    "/usr/bin/tesseract",
    "/usr/local/bin/tesseract",
]


@dataclass
class OcrLine:
    text: str
    conf: float
    bbox: tuple[float, float, float, float]  # normalised 0..1 on the deskewed image


@dataclass
class OcrResult:
    engine: str
    lines: list[OcrLine]
    angle: float
    steps: dict[str, np.ndarray] = field(default_factory=dict)  # name -> image (for the before/after viewer)

    @property
    def confidence(self) -> float:
        return float(np.mean([ln.conf for ln in self.lines])) if self.lines else 0.0

    @property
    def text(self) -> str:
        return "\n".join(ln.text for ln in self.lines)


# ------------------------------------------------------------------ preprocessing
def estimate_skew(binary_inv: np.ndarray, max_angle: float = 8.0, step: float = 0.25) -> float:
    """Angle (degrees) that maximises the variance of the horizontal projection profile."""
    h, w = binary_inv.shape
    scale = 800 / max(h, w)
    small = cv2.resize(binary_inv, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    center = (small.shape[1] / 2, small.shape[0] / 2)
    best, best_score = 0.0, -1.0
    for angle in np.arange(-max_angle, max_angle + step, step):
        m = cv2.getRotationMatrix2D(center, angle, 1.0)
        rot = cv2.warpAffine(
            small, m, (small.shape[1], small.shape[0]), flags=cv2.INTER_NEAREST, borderValue=0
        )
        score = float(np.var(rot.sum(axis=1)))
        if score > best_score:
            best, best_score = float(angle), score
    return best


def rotate(img: np.ndarray, angle: float, border: int = 255) -> np.ndarray:
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    return cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_CUBIC, borderValue=border)


def preprocess(path: Path) -> tuple[dict[str, np.ndarray], float]:
    original = cv2.imdecode(np.fromfile(str(path), dtype=np.uint8), cv2.IMREAD_COLOR)
    gray = cv2.cvtColor(original, cv2.COLOR_BGR2GRAY)
    denoised = cv2.fastNlMeansDenoising(gray, None, h=12, templateWindowSize=7, searchWindowSize=21)
    _, otsu_inv = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    angle = estimate_skew(otsu_inv)
    deskewed = rotate(denoised, angle, border=int(np.median(denoised)))
    binary = cv2.adaptiveThreshold(deskewed, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15)
    return {"original": gray, "denoised": denoised, "deskewed": deskewed, "binary": binary}, angle


# ------------------------------------------------------------------ OCR engines
@cache
def tesseract_cmd() -> str | None:
    found = shutil.which("tesseract") or next((p for p in TESSERACT_PATHS if Path(p).exists()), None)
    return found


@cache
def _easyocr_reader():
    import easyocr

    model_dir = settings.cache_dir / "easyocr"
    model_dir.mkdir(parents=True, exist_ok=True)
    return easyocr.Reader(
        ["en"], gpu=device() == "cuda", model_storage_directory=str(model_dir), verbose=False
    )


def available_engines() -> list[str]:
    return (["tesseract"] if tesseract_cmd() else []) + ["easyocr"]


def _group_lines(boxes: list[tuple[str, float, tuple]]) -> list[tuple[str, float, tuple]]:
    """Merge word/phrase boxes that share a baseline into lines (left-to-right)."""
    boxes = sorted(boxes, key=lambda b: (b[2][1] + b[2][3]) / 2)
    lines: list[list] = []
    for b in boxes:
        cy, hgt = (b[2][1] + b[2][3]) / 2, b[2][3] - b[2][1]
        for line in lines:
            lcy, lh = line[0], line[1]
            if abs(cy - lcy) < 0.5 * max(hgt, lh):
                line[2].append(b)
                break
        else:
            lines.append([cy, hgt, [b]])
    out = []
    for _, _, members in lines:
        members.sort(key=lambda b: b[2][0])
        text = " ".join(m[0] for m in members)
        conf = float(np.mean([m[1] for m in members]))
        x0 = min(m[2][0] for m in members)
        y0 = min(m[2][1] for m in members)
        x1 = max(m[2][2] for m in members)
        y1 = max(m[2][3] for m in members)
        out.append((text, conf, (x0, y0, x1, y1)))
    return out


def run_engine(img: np.ndarray, engine: str) -> list[OcrLine]:
    h, w = img.shape[:2]
    raw: list[tuple[str, float, tuple]] = []
    if engine == "tesseract":
        import pytesseract

        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd()
        d = pytesseract.image_to_data(img, config="--psm 11", output_type=pytesseract.Output.DICT)
        for i, word in enumerate(d["text"]):
            if word.strip() and float(d["conf"][i]) >= 0:
                x, y, bw, bh = d["left"][i], d["top"][i], d["width"][i], d["height"][i]
                raw.append((word, float(d["conf"][i]) / 100, (x, y, x + bw, y + bh)))
    else:
        reader = _easyocr_reader()
        for pts, text, conf in reader.readtext(img, paragraph=False):
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            raw.append((text, float(conf), (min(xs), min(ys), max(xs), max(ys))))
        raw += _reread_empty_cells(raw, img, reader)
    return [
        OcrLine(text=fix_ocr_text(t.strip()), conf=round(c, 3), bbox=(b[0] / w, b[1] / h, b[2] / w, b[3] / h))
        for t, c, b in _group_lines(raw)
        if t.strip()
    ]


TITLE_BLOCK_LABELS = {"REV", "REVISION", "SCALE", "MATERIAL", "FINISH", "PART NO", "TITLE", "DATE", "DRAWN"}


def _reread_empty_cells(raw: list[tuple], img: np.ndarray, reader) -> list[tuple]:
    """Text detectors miss isolated single characters (e.g. revision 'C'). When a title-block label has nothing to
    its right on the same row, run the recogniser directly on that cell region."""
    extra = []
    w = img.shape[1]
    for text, _, (x0, y0, x1, y1) in raw:
        if text.strip().upper().rstrip(":") not in TITLE_BLOCK_LABELS:
            continue
        cy = (y0 + y1) / 2
        if any(b[0] > x1 and b[1] <= cy <= b[3] for _, _, b in raw):
            continue
        h = y1 - y0
        region = [
            int(x1 + 0.5 * h),
            int(min(w - 1, x1 + 12 * h)),
            int(max(0, y0 - 0.4 * h)),
            int(y1 + 0.4 * h),
        ]
        for _, t, c in reader.recognize(img, horizontal_list=[region], free_list=[], detail=1):
            if t.strip() and c >= 0.3:
                extra.append((t.strip(), float(c), (region[0], y0, region[1], y1)))
    return extra


_ALNUM = re.compile(r"\b(?=[A-Za-z0-9-]*\d)[A-Za-z0-9-]+\b")


def fix_ocr_text(text: str) -> str:
    """Domain-aware O/0 repair inside codes that contain digits (e.g. 'GF3O' -> 'GF30', 'BMS - 91020' -> 'BMS-91020')."""
    text = re.sub(r"\b([A-Z]{3}) - (\d{5})\b", r"\1-\2", text)
    # O -> 0 only after a digit, or before a digit when not preceded by a letter ('42CrMo4' stays as is)
    return _ALNUM.sub(lambda m: re.sub(r"(?<=\d)[Oo]|(?<![A-Za-z])[Oo](?=\d)", "0", m.group(0)), text)


def ocr(path: Path, engine: str = "auto", use_preprocessing: bool = True) -> OcrResult:
    engine = settings.ocr_engine if engine == "auto" else engine
    if engine == "auto":
        engine = available_engines()[0]
    steps, angle = preprocess(path)
    img = steps["binary"] if use_preprocessing else steps["original"]
    return OcrResult(engine=engine, lines=run_engine(img, engine), angle=angle, steps=steps)


def save_steps(result: OcrResult, out_dir: Path, max_side: int = 1600) -> dict[str, str]:
    """Write downscaled step images for the UI before/after viewer; returns name -> path relative to var/."""
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, img in result.steps.items():
        scale = min(1.0, max_side / max(img.shape[:2]))
        small = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else img
        p = out_dir / f"{name}.jpg"
        cv2.imencode(".jpg", small, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tofile(str(p))
        paths[name] = os.path.relpath(p, settings.var_dir).replace("\\", "/")
    return paths


# ------------------------------------------------------------------ structured fields
PART_RE = re.compile(r"\b([A-Z]{3})\s?-\s?(\d{5})\b")
FIELD_RES = {
    "part_number": re.compile(r"PART\s*N[O0]\.?\s*[:\-]?\s*([A-Z]{3}\s?-\s?\d{5})", re.I),
    "revision": re.compile(r"^\s*REV(?:ISION)?\.?\s*[:\-]?\s*([A-Z0-9]{1,2})\s*$", re.I | re.M),
    "material": re.compile(r"^\s*MATERIAL\s*[:\-]?\s*(.+?)\s*$", re.I | re.M),
    "title": re.compile(r"^\s*TITLE\s*[:\-]?\s*(.+?)\s*$", re.I | re.M),
    "finish": re.compile(r"^\s*FINISH\s*[:\-]?\s*(.+?)\s*$", re.I | re.M),
    "date": re.compile(r"^\s*DATE\s*[:\-]?\s*(\d{4}-\d{2}-\d{2})", re.I | re.M),
    "supplier": re.compile(r"^\s*Supplier\s*:?\s*(.+?)\s*$", re.I | re.M),
    "lot": re.compile(r"^\s*Lot\s*:?\s*([A-Z]-\d{2}-\d{4})", re.I | re.M),
    "decision": re.compile(r"DECISION\s*:?\s*(ACCEPT|REJECT)", re.I),
    "plant": re.compile(r"^\s*Plant\s*:?\s*(.+?)\s*$", re.I | re.M),
}


def extract_fields(text: str) -> dict[str, str]:
    """Title-block / form fields from OCR text (drawings: part no, rev, material; inspection records: lot, ...)."""
    out = {}
    for name, rx in FIELD_RES.items():
        m = rx.search(text)
        if m:
            val = m.group(1).strip()
            out[name] = (
                re.sub(r"\s+", "", val)
                if name == "part_number"
                else val.upper()
                if name == "revision"
                else val
            )
    if "part_number" not in out:
        m = PART_RE.search(text)
        if m:
            out["part_number"] = f"{m.group(1)}-{m.group(2)}"
    return out
