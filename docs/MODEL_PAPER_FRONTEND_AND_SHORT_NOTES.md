# Model Paper UI component — full documentation (including Short Notes)

This document describes the **frontend Model Paper page**, how it talks to the **model-paper-generation** service, and how **Short Notes** work end-to-end (RAG + LLM).

**Backend generation (Paper A / B):** **[`MODEL_PAPER_COMPLETE_GENERATION_GUIDE.md`](./MODEL_PAPER_COMPLETE_GENERATION_GUIDE.md)**

**Agentic pipeline (Paper A vs Paper B):** Both buttons invoke **`run_full_pipeline`** → **`AgentOrchestrator.run_pipeline()`** with **all** agents: **BlueprintAnalyst**, **ContentResearcher**, **QuestionWriter**, **QualityCritic**, coordinated by **`AgentOrchestrator`**. Paper type does **not** skip any agent; only **`options`** change (e.g. `num_slots`, `selected_papers`, `questions_only`). **Code-verified write-up + diagram:** **[`MODEL_PAPER_AGENTIC_PIPELINE_PAPER_A_B.md`](./MODEL_PAPER_AGENTIC_PIPELINE_PAPER_A_B.md)**. **Branch-level table (marks, validation, strip):** **`MODEL_PAPER_DEEP_PER_PAPER.md` §1.1**.

---

## 1. Component location and role

| Item | Detail |
|------|--------|
| **React page** | `frontend/src/pages/ModelPaperPage.jsx` |
| **Styles** | `frontend/src/pages/ModelPaperPage.css` |
| **Layout shell** | `CommonHeader` |
| **Purpose** | Upload past papers & lecture slides; configure Paper B; run **Paper A** or **Paper B** generation; preview latest paper; download PDF; open **Short Notes** per question. |

---

## 2. API base URL

| Source | Value |
|--------|--------|
| Env | `import.meta.env.VITE_PAPERS_API_URL` |
| Fallback | `/papers` (e.g. when the app is behind an API gateway that proxies to the papers service) |

All `fetch` calls use **`API_BASE`** as prefix (e.g. `` `${API_BASE}/model-paper/generate-paper` ``).

---

## 3. API endpoints used by the UI

| Method | Path (relative to `API_BASE`) | Used for |
|--------|------------------------------|----------|
| `GET` | `/files` | List `past_papers` and `lecture_slides` filenames after upload |
| `POST` | `/past-papers/upload` | Upload a past-paper PDF (`multipart/form-data`, field `file`) |
| `POST` | `/lecture-slides/upload` | Upload lecture slide PDFs |
| `POST` | `/model-paper/generate-paper-a` | **Paper A** — no body |
| `POST` | `/model-paper/generate-paper` | **Paper B** — JSON body (see §4) |
| `GET` | `/model-paper/paper-json` | Load latest generated paper (on mount + error fallback) |
| `GET` | `/model-paper/download-pdf` | Open PDF in new tab (`window.open`) |
| `GET` | `/model-paper/diagram-image?question_no=Q1` | Image URL for diagram in preview (`<img src=...>`) |
| `GET` | `/model-paper/short-notes/{question_no}` | **Short Notes** for `Q1`, `Q2`, … (see §6) |

**Backend implementation:**  
- Model paper routes: `backend/services/model-paper-generation/app/api/routes/endpoints/model_paper.py`  
- File listing: `app/api/routes/endpoints/files.py` (prefix `/files`)  
- Uploads: `past_papers.py`, `lecture_slides.py`  

---

## 4. Paper B request payload (custom generation)

Built in `generatePaper()`:

```json
{
  "num_slots": <1–8>,
  "selected_papers": [{ "year", "sem", "file" }, ...],
  "semester_bias": "both" | "sem1" | "sem2",
  "questions_only": true
}
```

- **`selected_papers`:** From `computeSelectedPapers()` — checked files only; must have `20xx` in filename or they are filtered out. Semester logic applies when both sem I and II exist for a year.
- **`questions_only`:** Ensures saved JSON/PDF omit marks (backend strips marks after generation).

**Paper A** does not send a body; the server sets options (see complete generation guide).

---

## 5. UI flows (step-by-step)

### 5.1 Initial load

1. `useEffect` → `checkLatestPaper()` → `GET /model-paper/paper-json` (if 200, sets preview state).  
2. `fetchFiles()` → `GET /files` → populates past papers / slides lists.  
3. `useEffect` on `files.past_papers`: new files default to **selected** in `paperFileSelection`.

### 5.2 Upload

- Validates `.pdf` extension client-side.  
- `FormData` + `POST` to `/past-papers/upload` or `/lecture-slides/upload`.  
- On success, `fetchFiles()` refreshes lists.

### 5.3 Generation settings (Paper B only)

- **Stepper:** `numSlots` 1–8.  
- **Past paper checkboxes** + Select all / Clear.  
- **Semester pills:** both / sem1 / sem2.  
- **Stats row:** derived count of selected papers, `numSlots`, semester label.

### 5.4 Generate Paper A

- `POST /model-paper/generate-paper-a`.  
- Logs `data.steps` if present.  
- On success: `setPaper(data.paper)`; if `data.paper_a_slot_inference` exists, logs mode / fallback info.

### 5.5 Generate Paper B

- `POST /model-paper/generate-paper` with payload in §4.  
- On failure, may still `GET /paper-json` to show last disk snapshot.

### 5.6 Preview

- Renders `paper.questions`: stem, optional diagram (`diagram_image_path` + `diagram_generated`), subquestions (and nested).  
- Question headers show **`(N marks)`** only when `q.marks` is present and &gt; 0 (aligns with Paper B questions-only output).

### 5.7 Download PDF

- `window.open(`${API_BASE}/model-paper/download-pdf`)` — server regenerates PDF from latest JSON so it matches preview.

---

## 6. Short Notes — how it works

Short Notes are **not** part of the main generate pipeline. They run **on demand** when the user clicks **Short Notes** on a question in the preview.

### 6.0 Which agents / components are used

Short Notes reuse **only one** of the same `BaseAgent` classes as full paper generation:

| Component | Used? | Role |
|-----------|-------|------|
| **`ContentResearcher`** (`app/agents/researcher.py`) | **Yes** | Same agent as in `AgentOrchestrator`: embed query → FAISS over slide chunks → optional **`_summarize_hits`** (first LLM pass, `temperature: 0.3`) → returns evidence text to the route. |
| **`QuestionWriter`** | **No** | Not invoked for Short Notes. |
| **`QualityCritic`** | **No** | Not invoked for Short Notes. |
| **`BlueprintAnalyst`** | **No** | Not invoked for Short Notes. |
| **`AgentOrchestrator` / `run_pipeline()`** | **No** | Short Notes do not run the orchestrator; they are a separate FastAPI handler. |
| **`get_short_notes` route + LLM** (`model_paper.py`) | **Yes** | Second **chat completion** (not routed through Writer): formats curriculum-aligned markdown short notes (`temperature: 0.4`). |

So: **retrieval agent = `ContentResearcher` only**; **final note text = direct LLM call in the API route**, not Writer/Critic.

### 6.1 User flow (frontend)

1. User clicks **Short Notes** on question `q` (`q.question_no` e.g. `Q1`).  
2. `fetchShortNotes(questionNo, question)` runs:  
   - Opens modal (`showNotesModal`), sets loading.  
   - **`GET /model-paper/short-notes/{question_no}`** — path uses the question id (e.g. `Q1`; server normalizes with `.upper()`).  
3. Response JSON field **`short_notes`** (Markdown-style string from the LLM) is passed through a **small client-side transform** (regex) before `dangerouslySetInnerHTML`: `**bold**`, `*italic*`, `#` / `##` / `###` headings, `- ` list lines, and newlines → `<br>`. This is not a full Markdown parser; complex tables may not render perfectly.

### 6.2 Backend flow (`get_short_notes` in `model_paper.py`)

| Step | What happens |
|------|----------------|
| **1** | Load **`data/outputs/model_papers/agentic_model_paper.json`**. |
| **2** | Find the question where `question_no` matches (case-insensitive). |
| **3** | Build a **search query** from question stem + all subquestion texts, concatenated, **truncated to 1000 chars**. |
| **4** | **`ContentResearcher`** (`app/agents/researcher.py`) with **`top_k: 8`**: embed query with **SentenceTransformer** (`all-MiniLM-L6-v2`), **FAISS** search over **lecture slide** chunks (`slides_chunks.jsonl` + index from `lectureslide_extract`). When the LLM client is available, **`_summarize_hits`** runs a **first LLM pass** (`temperature: 0.3`) to extract evidence from retrieved chunks; otherwise the route receives **raw** formatted chunk text. |
| **5** | If retrieval/summary output is empty → **503** with message to upload/index slides. |
| **6** | **Second LLM** call (`get_llm_client()`, `settings.OPENAI_MODEL` or `gpt-4o-mini`): system + user prompt asks for **curriculum-aligned short notes** (definitions, examples, formulas, markdown sections). Lecture context capped (~6000 chars) in the prompt. **`temperature: 0.4`**. |
| **7** | Return JSON: `question_no`, `question_text`, `short_notes`, `source: "RAG from lecture slides"`. |

### 6.3 Prerequisites for Short Notes

- A **generated paper** must exist (`agentic_model_paper.json`) with the target `question_no`.  
- **Lecture slides** must have been processed so **FAISS index + chunks** exist (full pipeline or slide extract script).  
- **LLM API** configured (`llm_factory` / env) — same stack as writer/critic.

### 6.4 Technologies — Short Notes

| Layer | Technology |
|-------|------------|
| Retrieval | **Sentence-BERT** (MiniLM) embeddings + **FAISS** flat index over slide chunks |
| Generation | **OpenAI-compatible chat completions** (model from settings); up to **two** calls when the client is configured (researcher evidence extraction **0.3**, then short-notes synthesis **0.4**) |
| Agents | **`ContentResearcher` only** (Writer, Critic, Analyst, Orchestrator **not** used) |
| Orchestration | FastAPI `get_short_notes` handler + LLM client (see §6.0) |
| Data | Latest paper JSON on disk; slide artifacts under `data/` (see `app.core.paths`) |

---

## 7. Technologies — Model Paper page (summary)

| Area | Stack |
|------|--------|
| UI | **React** (hooks: `useState`, `useEffect`), JSX |
| HTTP | **`fetch`**, JSON, `FormData` for uploads |
| Routing | Page is a route in your app router (e.g. React Router) — path depends on project setup |
| Styling | Global stylesheet `ModelPaperPage.css` imported in `ModelPaperPage.jsx` (not CSS Modules) — cards, stepper, pills, modal |
| Backend peer | **FastAPI** service: model paper, files, past-papers, lecture-slides routers |

---

## 8. State snapshot (`ModelPaperPage.jsx`)

| State | Role |
|-------|------|
| `logs`, `status`, `processing` | Generation progress / errors |
| `paper` | Latest paper object for preview |
| `files` | `{ past_papers, lecture_slides }` from `/files` |
| `numSlots`, `semesterBias`, `paperFileSelection` | Paper B settings |
| `showNotesModal`, `selectedQuestion`, `shortNotes`, `loadingNotes` | Short Notes modal |
| `notification` | Upload validation popup |

---

## 9. Related files (quick index)

| File | Role |
|------|------|
| `frontend/src/pages/ModelPaperPage.jsx` | Main UI |
| `frontend/src/pages/ModelPaperPage.css` | Styles |
| `frontend/src/pages/DashboardHome.jsx` | Links/copy mentioning model papers + short notes |
| `app/api/routes/endpoints/model_paper.py` | Generate A/B, paper-json, PDF, diagram, **short-notes** |
| `app/api/routes/endpoints/files.py` | `GET /files` |
| `app/agents/researcher.py` | FAISS + embeddings retrieval (shared with orchestrator + short notes) |
| `app/core/llm_factory.py` | LLM client for short notes synthesis |

---

*Last aligned with codebase patterns for model-paper-generation + ModelPaperPage. If short-notes response format is markdown vs HTML, adjust preview rendering or LLM instructions for consistency.*
