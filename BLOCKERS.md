# Blockers / things waiting on the user

| # | Item | Impact | What I did | What you need to do |
|---|---|---|---|---|
| 1 | `GROQ_API_KEY` and `GOOGLE_API_KEY` in `.env` are empty | Needed from P3 (LLM answers, eval judge) | Built P0–P2 without them | Fill both in `C:\dev\yokoten\.env` (keys from https://console.groq.com/keys and https://aistudio.google.com/apikey) |
| 2 | Ollama not installed | Local "on-prem" LLM mode unavailable | Skipped local mode; Groq is the default | `setx OLLAMA_MODELS "D:\ollama\models"`, then `winget install --id Ollama.Ollama -e` |
| 3 | Tesseract not installed | OCR uses EasyOCR; Tesseract vs EasyOCR comparison can't run yet | OCR code auto-detects Tesseract at `C:\Program Files\Tesseract-OCR` | `winget install --id UB-Mannheim.TesseractOCR -e` |
| 4 | Docker Desktop not installed | Docker build can't be verified locally | Dockerfiles + compose written; will verify in P7 | Install before P7 (move its disk image to D:) |
