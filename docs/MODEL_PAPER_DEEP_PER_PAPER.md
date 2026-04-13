# Deep documentation: what happens in Paper A vs Paper B

This document explains **in detail** what the system does when you generate **Paper A** (standard) or **Paper B** (custom). Both use the **same code path** (`run_full_pipeline` → `AgentOrchestrator.run_pipeline`); differences come from the **`options`** dict built by the API or the frontend.

**Most complete single reference:** **[`MODEL_PAPER_COMPLETE_GENERATION_GUIDE.md`](./MODEL_PAPER_COMPLETE_GENERATION_GUIDE.md)**.

**UI + Short Notes:** **[`MODEL_PAPER_FRONTEND_AND_SHORT_NOTES.md`](./MODEL_PAPER_FRONTEND_AND_SHORT_NOTES.md)** (which agents Short Notes use: **§6.0**).

**Paper A & B — same agentic pipeline (all agents, code-verified):** **[`MODEL_PAPER_AGENTIC_PIPELINE_PAPER_A_B.md`](./MODEL_PAPER_AGENTIC_PIPELINE_PAPER_A_B.md)**.

For a shorter comparison table, see **`MODEL_PAPER_A_AND_B.md`**.

---

## 1. Same skeleton for both papers

When either paper is generated:

1. **`pipeline_service.run_full_pipeline(options)`** runs.
2. **Phase 1 — `process_uploaded_files()`**  
   - Processes every past-paper PDF and lecture-slide PDF found in configured folders.  
   - Runs extraction scripts, structure/topic scripts, template analysis, and (if possible) MongoDB migration.  
   - Produces/updates **artifacts** (blueprint JSON, trend summaries, canonical templates, per-paper blueprints under `text_extraction_hybrid/<stem>/`, etc.).
3. **Phase 2 — `run_agentic_generation(options)`**  
   - Calls **`orchestrator.main(options)`** → **`AgentOrchestrator(options).run_pipeline()`**.

So: **one full preprocessing pass + one full agentic run** per button press. The only variable passed into the agentic phase is **`options`**.

### 1.1 Agentic pipeline — which parts Paper A and Paper B use

**Paper A and Paper B both run the same agentic code path:** `AgentOrchestrator.run_pipeline()` in `app/agents/orchestrator.py`. There is **no** separate or shortened pipeline for either paper; every stage below executes for both. What changes is **how `options` steer** a few branches (trend source, template Mongo filter, validation, final JSON shape).

| Agentic stage / component | Code reference (typical) | Paper A | Paper B |
|---------------------------|---------------------------|---------|---------|
| **Blueprint analyst** | `BlueprintAnalyst.run()` | Loads/validates blueprint; trims or pads slots to **`num_slots`** (mode-derived **1–8**). | Same; **`num_slots`** is user **1–8**. |
| **Trend & topic planning** | `_load_trend_for_request()` **or** `_load_lecture_slide_trend()`, `_preview_slot_intents`, `enforce_top_topic_constraint`, `_pick_topics_for_slots` | **Same code.** Trend from **past-paper** blueprints for **all** stems in `selected_papers`. | **Default:** trend from **lecture** chunks — **MiniLM embeddings + KMeans** (`lecture_topic_trend_service`), mapped to pattern labels → `top_topic` / `topic_frequencies`. Set **`lecture_based_topics: false`** on `POST /generate-paper` to use **past-paper** trends from `selected_papers` instead. |
| **Per-slot loop** | Checkpoint read/skip; `_get_canonical_template`; template resolution + `_select_template` | **Same loop.** | **Same loop.** |
| **Content researcher** | `ContentResearcher.run()` (FAISS + slides) | **Same** retrieval for every slot. | **Same.** |
| **Question writer** | `QuestionWriter.run()` | **Same** drafting (uses slot marks internally). | **Same** pipeline; with lecture-based topics, prompts add **lecture-driven creative** instructions (`lecture_creative_mode`). |
| **Quality critic** | `QualityCritic.run()` + retry / paraphrase | **Same** per-question review. | **Same.** |
| **Deterministic fixes & diagram generation** | Post-writer normalization; diagram service when flagged | **Same** where applicable. | **Same.** |
| **Mongo template `marks` filter (±5)** | `_select_template` when falling back to DB | **Applied** (`questions_only` is false). | **Not applied** when **`questions_only`** is true (templates still chosen by topic/diversity). |
| **Global paper validation** | `validate_model_paper(..., questions_only=…)` | **Full rules:** numbering, topics, **marks math**, **100** total. | With **`questions_only`:** **marks-related checks skipped** (numbering/topic rules still apply as implemented). |
| **Repair loop** | `repair_model_paper` on validation failure | **Same** mechanism if triggered. | **Same.** |
| **Presentation normalization** | `_normalize_paper_for_presentation` | **Same** (e.g. JDBC/Q4 wording). | **Same.** |
| **Strip marks from artifact** | `_strip_marks_from_paper` | **Not called** — marks stay in JSON/PDF. | **Called** when **`questions_only`** — saved output has no marks fields. |
| **Persist** | Mongo `papers`, `agentic_model_paper.json`, `PDFService.generate_pdf`, checkpoint delete | **Same** persistence path. | **Same** path; stored paper content reflects stripped marks when applicable. |

**Summary:** Both papers use **Analyst → trend/planning → per-slot (Researcher + Writer + Critic + diagrams) → validate → normalize → persist/PDF**. Paper A vs B differences include **`num_slots` source**, **trend source** (past papers vs default lecture clustering for Paper B), **Mongo marks band on template fallback**, **validation strictness for marks**, and **whether marks are stripped** before save.

### 1.2 Confirmation: all four `BaseAgent` classes run for both papers

`AgentOrchestrator.__init__` always constructs **`BlueprintAnalyst`**, **`ContentResearcher`**, **`QuestionWriter`**, and **`QualityCritic`** regardless of `options`. **`run_pipeline()`** calls **`analyst.run()`** once, then for each question slot invokes **`researcher.run()`**, **`writer.run()`**, and **`critic.run()`** (with retries) on the same code path for Paper A and Paper B. For citations, API entry points, and a Mermaid diagram, see **`MODEL_PAPER_AGENTIC_PIPELINE_PAPER_A_B.md`**.

---

## 2. Paper A — what happens (end-to-end)

### 2.1 User / API trigger

- **Endpoint:** `POST /model-paper/generate-paper-a`  
- **Body:** none.  
- **Server builds `options` roughly as:**

```text
num_slots          → MODE of question counts from past papers in the last 6 years (blueprints);
                     multimodal tie → smallest; clamp 1–8; fallback 4
semester_bias      → "both" (fixed)
selected_papers    → one entry per *.pdf / *.PDF in the past-papers directory
                     each item: { year, sem, file } parsed from filename
questions_only     → omitted (treated as false)
```

**Effect:** Question count matches the **most frequent** paper length in the **6-year window** used by `paper_a_dynamic_slots.py` (e.g. counts 4,4,4,5,6 → 4). **Generating** those questions is **not** limited to 6 years: **`_load_trend_for_request()`** uses **all** PDFs in `selected_papers` (Paper A = entire folder) that have cached blueprints — **no** 6-year filter on that path.

### 2.2 Preprocessing phase (shared)

Roughly in order:

| Step | Purpose |
|------|---------|
| Past paper PDFs | Extract text/OCR, hybrid pipeline, build per-paper structures |
| Lecture slides | Extract content for supplementary knowledge |
| `structure_topics_template` | Exam blueprint template, topic clustering, **`trend_summary.json`** (often from “recent” papers in that script) |
| `template_analyzer` | Canonical / pattern templates used at generation time |
| `migrate_data` | Push templates into MongoDB for `_select_template` |

Paper A does **not** skip any of this; it is identical to Paper B for this phase.

### 2.3 Agentic phase — configuration that is *specific* to Paper A

| Setting | Paper A behavior |
|---------|-------------------|
| **`num_slots`** | From **`compute_paper_a_num_slots_from_recent_papers()`** (mode of Q-counts, **last 6 years only for this statistic**); blueprint trimmed or padded to that count (clamped 1–8). |
| **`selected_papers`** | **All** PDFs → `_load_trend_for_request()` loads blueprints for **every** stem and recomputes **`top_topic`**, **topic frequencies**, **`recent_papers_used`**, etc. |
| **`semester_bias`** | Only affects **frontend** selection for Paper B; for Paper A the API always sends **`both`** semantics by including **all** files (no sem filtering at API). |
| **`questions_only`** | **False** → Mongo template query can filter by **marks ±5**; **`validate_model_paper`** enforces marks consistency and **100** total marks; output JSON/PDF **include** all marks. |

### 2.4 Agentic phase — step-by-step (orchestrator)

Below is the logical order inside **`run_pipeline()`** (same code for A and B; Paper A is the instance where the flags above take their “standard” values).

#### Step A — Blueprint (Analyst)

- **`BlueprintAnalyst.run()`** loads **`exam_blueprint_template.json`** from artifacts (produced in preprocessing).
- Slots are validated/repaired (valid `target_marks`, `question_no` / `slot_id`, `type`, etc.).
- Orchestrator sets **`target_q_count = num_slots`** → for Paper A this is the **mode-based** value (1–8), so slots are trimmed or padded to match.

#### Step B — Trend and topic planning

- **`trend = await _load_trend_for_request()`**  
  - Paper A: **`selected_papers`** is the full list → trend = frequencies from **all** those papers’ cached blueprint files.
- **`top_topic`** defaults from trend or **`GENERAL_THEORY`**.
- **`_preview_slot_intents`** reads canonical intent per slot (Q1…).
- If no canonical slot already covers **`top_topic`**, the orchestrator **forces** `forced_pattern_label = top_topic` on the slot with the **most Mongo templates** matching that topic and **`target_marks`** (marks used here only for **counting** candidates).
- **`enforce_top_topic_constraint`** ensures at least one slot is aligned with **`top_topic`** when needed.
- **Checkpoint** file may be loaded to **resume** partially generated papers (same for A and B).

#### Step C — Per-slot topic hints

- **`_pick_topics_for_slots(trend, target_q_count)`** builds a deterministic list of desired topics from **frequency order**, promoting **`top_topic`** first.
- For each slot **without** an existing **`forced_pattern_label`**, that list may set **`forced_pattern_label`** for diversity.

#### Step D — For each slot (Q1 … Qn)

For each question position (Paper A: **`num_slots`** iterations, typically 4 if mode is 4):

1. **Checkpoint skip** — if this `question_no` already exists in the checkpoint JSON, the slot is skipped.
2. **Canonical template** — **`_get_canonical_template(q_no)`** loads the data-driven template for that slot (topic/structure from mined statistics, **not** “Q1 is always ER” by position alone).
3. **Template resolution**  
   - Prefer canonical structure (`subquestion_structure`, marks, pattern_label).  
   - If canonical would duplicate an already-used intent/template id, fall back to **`_select_template`** with diversity constraints (`used_intents`, `used_template_ids`, banned topics).  
   - **Paper A:** `_select_template` applies a **Mongo `$match` on `marks`** within **±5** of `target_marks` when marks are present.
4. **Researcher** — **`ContentResearcher.run()`** with a query built from exam title, slot topic, and template pattern (retrieval/context for the writer).
5. **Writer / Critic loop** (up to **`MAX_RETRIES`**)  
   - **`QuestionWriter.run()`** with slot, template, context, anti-repetition **`global_context`**, diagram flags (**`needs_diagram`**, **`diagram_type`** for Q1 ER/EER when template text implies “following diagram”), aggregation specs for EER, etc.  
   - Draft is **sanitized**, **`pattern_label` / `main_topic` / `intent`** aligned to the template.  
   - **Deterministic fixes** may run (e.g. Q1 entity attributes, Q3 schema/table consistency, Q4 structure, heavy Q3 subquestion normalization) **before** or **after** critic depending on code path.  
   - **`QualityCritic.run()`** approves or returns feedback; on failure, writer retries in **paraphrase** mode.
6. **Diagram generation** (when flagged) for Q1-style “show diagram” questions.
7. **Append** draft to **`final_questions`**; update **anti-repetition** sets (`used_topics`, `banned_topics`, `used_question_types`, etc.).
8. **Checkpoint write** — `generation_checkpoint.json` updated so a failed run can resume.

#### Step E — After all slots

- **`_validate_topic_coverage`** — logs / checks topic spread.
- **Sort** questions by **`question_no`** (Q1, Q2, …).
- **Build `paper` dict:** `generated_at`, `mode`, **`total_marks`**, `topic_distribution`, `questions`.
- **`validate_model_paper(..., questions_only=False)`** for Paper A:  
  - Correct **number** of questions and **Q1..Qn** numbering.  
  - Topic rules (e.g. max twice per topic, top topic presence when required).  
  - **Marks:** each question has positive marks; subquestion sums match; paper total matches sum; **total equals 100**.
- On validation errors: **`repair_model_paper`** (regenerate offending slots with topic constraints), then re-validate (bounded retries).
- **`_normalize_paper_for_presentation`** — e.g. fixed Q3 JDBC part (b) wording, Q4(a) lead-in trim.
- **Paper A does not call `_strip_marks_from_paper`.**
- **Persist:** insert into MongoDB **`papers`**, write **`agentic_model_paper.json`**, **`PDFService.generate_pdf`**, delete checkpoint.

**Result for Paper A:** A paper with **`num_slots`** questions (mode-derived), JSON and PDF with **full marks**, validated to **100** marks, with trends reflecting **all** past papers in the folder.

---

## 3. Paper B — what happens (end-to-end)

### 3.1 User / API trigger

- **Endpoint:** `POST /model-paper/generate-paper`  
- **Body:** JSON from the UI (or any client), typically:

```text
num_slots              → 1–8 (user stepper)
selected_papers        → only checked files, after year + semester_bias rules
semester_bias          → "both" | "sem1" | "sem2"
questions_only         → true (from current ModelPaperPage)
lecture_based_topics   → omitted on API → defaults to true (topics from lecture MiniLM+KMeans); false = past-paper trend from selected_papers
```

(Other optional fields on **`GeneratePaperRequest`** are passed through if present.)

### 3.2 Preprocessing phase

**Identical to Paper A** for the same codebase path: full **`process_uploaded_files()`** runs first.

### 3.3 Agentic phase — configuration that is *specific* to Paper B

| Setting | Paper B behavior |
|---------|-------------------|
| **`num_slots`** | User-chosen **1–8**. Blueprint **trimmed** if fewer slots needed, or **padded** with generic slots (`DEFAULT_SLOT_MARKS`, topics `["General"]`, type `conceptual`) for Q5+. |
| **`lecture_based_topics`** | **Default `true`** from `POST /generate-paper`: **`_load_lecture_slide_trend()`** reads **`slides_chunks.jsonl`**, embeds with **MiniLM**, **KMeans**, maps clusters to pattern labels → **`top_topic`** / **`topic_frequencies`**. If **`false`**, uses **`_load_trend_for_request()`** on **`selected_papers`** blueprints (subset of past papers). |
| **`selected_papers`** | Still used for UI scope / optional past-paper trend when **`lecture_based_topics: false`**. Does **not** drive topic mining when lecture mode is on. |
| **`semester_bias`** | Applied on the **frontend** when building **`selected_papers`** (which files appear in the list at all). |
| **`questions_only`** | **True** (current UI) → see §3.5. |

### 3.4 Agentic per-slot loop (Paper B)

The **same** steps A–D as Paper A (blueprint → trend → slots → per-slot researcher/writer/critic/checkpoint).

**Difference inside template selection only:**

- When **`questions_only`** is true, **`_select_template`** **does not** add the Mongo match on **`marks`** in the ±5 band. Templates are chosen by topic/diversity/quality without that marks filter (internal **`target_marks`** still exist on slots for writer structure and for `_count_templates_for_topic` during top-topic slot choice).

All Q1/Q3/Q4 post-processing, critic loops, and checkpointing behave the **same** unless you change code.

### 3.5 Paper B — finalization (`questions_only`)

After the paper passes **`validate_model_paper`** with **`questions_only=True`**:

- **Marks-related checks are skipped** during validation (no per-question marks>0, no sub-sum equality, no **100**-mark total requirement).
- **`_strip_marks_from_paper`** runs: removes **`marks`** from every question and nested subquestion, removes **`total_marks`**, and removes **`marks`** from **`topic_distribution`** entries.
- **`_normalize_paper_for_presentation`** still runs (same JDBC/Q4 rules).
- JSON and PDF are produced from the **stripped** paper. **PDF** renders headers as **`Q1`** without **`(N marks)`** when marks are absent.

**Important:** Internally, the writer/critic may still use **marks** during generation; only the **published** artifact is questions-only.

**Result for Paper B:** A paper with **N** questions (1–8); **default** topic/trend signal from **lecture** clustering (MiniLM + KMeans); **no marks** in saved JSON/PDF when `questions_only`; **no strict marks math** on the final artifact. Use **`lecture_based_topics: false`** to drive trends from **selected** past papers instead.

### 3.6 Paper B — writer prompt goals (lecture-aligned, creative, complex)

When **`lecture_based_topics`** is enabled (default for **`POST /model-paper/generate-paper`**), the orchestrator sets **`lecture_creative_mode`** in the **`QuestionWriter`** `global_context`. The writer then appends an extra instruction block in **`app/agents/writer.py`** (generation and paraphrase/revision paths). Intent for future maintainers:

| Goal | What the prompts steer the LLM to do |
|------|----------------------------------------|
| **Lecture as primary syllabus signal** | Treat **retrieved slide context** (FAISS + **ContentResearcher**) as the main guide for topics such as SQL, normalization, ER/EER, transactions, indexing, etc., rather than copying past-paper scenarios. |
| **Creative, applied tasks** | Use **fresh real-world domains** (e.g. university, hospital, e-commerce) and new entity/schema names; keep **template question type** and **required structure** (sub-part count, instruction patterns, marks per part) from Mongo/canonical templates. |
| **Bloom’s taxonomy & marks** | Spread cognitive demand across sub-parts: lighter **recall/understand** where marks are low; **apply** (e.g. write SQL/RA, concrete steps); **analyze / synthesize / evaluate** for **higher-mark** parts (design, justify, compare, integrated scenarios). |
| **Multi-step & problem-solving** | Prefer **multi-step, scenario-based** stems over theory-only papers; align difficulty with **per-subquestion marks** where the template exposes them. |
| **Consistency with “historical” wording** | Global prompt text still refers to historical patterns for **structure**; the Paper B block clarifies that **scenario and topic emphasis** follow **lecture + applied tasks**, while **structure and patterns** stay template-faithful. |
| **No solutions in the stem** | Unchanged system rules: **no** full answers, hints, or leaked approaches in the question text. |
| **Paraphrase / revision mode** | After **QualityCritic** feedback, the same Paper B block (short form) reinforces **lecture-grounded**, **applied**, **multi-step** fixes without breaking structure or marks. |

**Code reference:** `QuestionWriter.run()` → `lecture_creative_mode` from `global_context`; `_build_generation_prompt` and `_build_paraphrase_prompt` — search for **`PAPER B — LECTURE-ALIGNED`**.

---

## 4. Side-by-side: “what differs” in one table

| Stage | Paper A | Paper B |
|-------|---------|---------|
| Preprocessing | Full run | Full run (same) |
| `options.num_slots` | **Mode-derived** from recent papers (clamped **1–8**); not a fixed count | User-chosen **1–8** |
| `options.selected_papers` | All PDFs in folder | User-selected list |
| Trend / `top_topic` source | Past-paper blueprints (all listed stems) | **Default:** lecture `slides_chunks.jsonl` (MiniLM + KMeans). **Optional:** selected past papers if `lecture_based_topics: false` |
| Mongo template marks filter | On (±5 band) | Off when `questions_only` |
| `validate_model_paper` marks rules | Enforced | Skipped if `questions_only` |
| Output marks | Present | Stripped if `questions_only` |
| Expected question count | Same as inferred **`num_slots`** (1–8) | User **`num_slots`** |

---

## 5. Frontend-specific behavior (Paper B only)

- **File list** from **`GET /files`**; checkboxes default **on** for new files.  
- **`computeSelectedPapers()`** builds the **`selected_papers`** array using **year**, **semester**, and **`semesterBias`**.  
- **Paper A button** does not send this list; the **server** rebuilds “all PDFs” itself.

---

## 6. Resume and caching

- **Checkpoint:** `OUTPUTS_DIR/model_papers/generation_checkpoint.json` stores completed questions; a new run **skips** slots already present (same for A and B).  
- **Latest paper on disk:** `agentic_model_paper.json` / `.pdf` are **overwritten** on successful completion.

---

## 7. Key source files (for traceability)

| Concern | Location |
|---------|----------|
| Paper A route & options | `app/api/routes/endpoints/model_paper.py` → `generate_paper_a` |
| Paper B route & schema | `app/api/routes/endpoints/model_paper.py` → `generate_paper`, `GeneratePaperRequest` |
| Full pipeline | `app/services/pipeline_service.py` |
| Orchestrator entry | `app/agents/orchestrator.py` → `main`, `AgentOrchestrator.run_pipeline` |
| Trend from selection | `AgentOrchestrator._load_trend_for_request` |
| Paper B lecture topics | `AgentOrchestrator._load_lecture_slide_trend` → `app/services/lecture_topic_trend_service.py` |
| Paper B creative prompts | `app/agents/writer.py` (`lecture_creative_mode`; see §3.6) |
| Template marks filter | `AgentOrchestrator._select_template` |
| Validation & strip | `validate_model_paper`, `_strip_marks_from_paper` |
| Blueprint load | `app/agents/analyst.py` |
| PDF | `app/services/pdf_service.py` |
| UI | `frontend/src/pages/ModelPaperPage.jsx` |

---

*This deep doc is meant to align with the implementation as of the last codebase review; if you change `run_full_pipeline` to skip preprocessing, update §1 and §2.2 accordingly.*
