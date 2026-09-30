# Demo script — 3 minutes

Goal: show a recruiter / hiring manager that the chatbot answers from engineering documents, proves where each
answer came from, refuses to guess, handles scans, and that its accuracy is measured.

**Before recording:** `.\tasks.ps1 dev`; set a hosted LLM (Groq) in `.env` for fast answers; ask each demo question
once beforehand so the answers are cached; browser at 1440×900, light mode; role = Admin.

| Time | Screen | Do | Say |
|---|---|---|---|
| 0:00–0:15 | Landing `/` | Scroll hero → metrics strip | "New engineers lose hours finding past failures. Yokoten answers from the engineering record - 8Ds, lessons learned, FMEAs, test reports, scans - with citations, and it is measured." |
| 0:15–0:45 | `/chat` | Click example *"What was the root cause of the inverter power module solder fatigue on project P-INV-2104?"* | "Answers stream in; every sentence is cited." Click citation **[1]** → source viewer opens the PDF page with the passage highlighted. "Straight to the evidence." |
| 0:45–1:05 | Chat | Type follow-up *"How was it contained?"* | "Follow-ups work - the question is rewritten with the context of the conversation." Point at *Interpreted as*. |
| 1:05–1:25 | Chat | Click **Trace** | "Every answer is explainable: rewritten query, filters, each chunk's dense, BM25, fused and rerank scores, latency per stage, and the NLI check of every sentence." |
| 1:25–1:40 | Chat | Ask *"What was the warranty cost in US dollars of the inverter solder fatigue issue?"* | "Not in the documents, so it says so instead of inventing a number - and shows the closest documents." |
| 1:40–2:00 | Chat | Ask *"What material is specified on the drawing of part RAD-30512?"* → open source | "This answer exists only in a scanned drawing. OpenCV cleans and deskews the scan, OCR reads the title block." Library → OCR tab → drag the before/after slider. |
| 2:00–2:15 | Chat | Ask *"How many 8D reports were opened for traction inverters?"* | "Counting questions go to text-to-SQL over structured tables; the SQL is shown." |
| 2:15–2:30 | Header | Switch role to **New engineer**, ask about the field failure analysis | "Access control: restricted documents are never retrieved for this role." Switch back to Admin; as Quality SME click **Verify** on an answer. |
| 2:30–2:50 | `/eval` | Show headline cards → Ablations tab → Error analysis | "129-question golden set, split into dev and test. Hybrid retrieval, reranking and chunking were chosen by ablation; failures are analysed, not hidden." |
| 2:50–3:00 | `/onboarding` | Build brief for *traction inverter* | "And for a new engineer: a cited onboarding brief per product. Everything runs on a laptop CPU; the LLM can be local so data never leaves the plant." |

**Recording tips:** 1080p, hide bookmarks, zoom 110 %, cursor highlight on. Export a 20–30 s GIF of the chat →
citation → source viewer sequence for the README (`docs/demo.gif`).
