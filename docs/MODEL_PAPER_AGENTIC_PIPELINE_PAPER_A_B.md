# Paper A & Paper B — same agentic pipeline (code-verified)

This document confirms that **Paper A** and **Paper B** both execute the **full agentic pipeline** with **all** coordinator and agent components. Neither paper type uses a shortened graph, alternate orchestrator, or subset of agents.

**Related docs:** **[`MODEL_PAPER_DEEP_PER_PAPER.md`](./MODEL_PAPER_DEEP_PER_PAPER.md)** (end-to-end behaviour + options table §1.1), **[`MODEL_PAPER_FRONTEND_AND_SHORT_NOTES.md`](./MODEL_PAPER_FRONTEND_AND_SHORT_NOTES.md)** (UI triggers).

---

## 1. Code-level verification

### 1.1 Same entry point for both papers

| Paper | HTTP route | Agentic entry |
|-------|------------|----------------|
| **Paper A** | `POST /model-paper/generate-paper-a` | `pipeline_service.run_full_pipeline(options=…)` |
| **Paper B** | `POST /model-paper/generate-paper` | `pipeline_service.run_full_pipeline(options=…)` |

Implementation: `backend/services/model-paper-generation/app/api/routes/endpoints/model_paper.py`

- Paper A builds `options` (e.g. `num_slots`, `selected_papers` = all PDFs) and calls **`run_full_pipeline(options=options)`** (~line 69).
- Paper B passes the request body as **`options`** via **`run_full_pipeline(options=options)`** (~line 83).

So **both** always go through the same two phases:

1. **`process_uploaded_files()`** — preprocessing (not agent classes; scripts + artifacts).
2. **`run_agentic_generation(options)`** — agents.

### 1.2 Same agentic function for any `options`

`backend/services/model-paper-generation/app/services/pipeline_service.py`:

- **`run_agentic_generation`** imports **`orchestrator.main`** and runs **`await agentic_main(options=options or {})`** — no branch on “Paper A” vs “Paper B”.
- **`main`** in `orchestrator.py` is **`AgentOrchestrator(options).run_pipeline()`**.

Therefore **every** successful generation (A or B) runs **`AgentOrchestrator.run_pipeline()`** with only the **`options`** dict differing.

### 1.3 All agents are constructed for every run

`AgentOrchestrator.__init__` in `backend/services/model-paper-generation/app/agents/orchestrator.py` **always** creates:

| Member | Class | Role |
|--------|-------|------|
| `self.analyst` | `BlueprintAnalyst` | Load/validate blueprint (`exam_blueprint_template.json`). |
| `self.researcher` | `ContentResearcher` | Slide retrieval (embeddings + FAISS; optional LLM evidence pass). |
| `self.writer` | `QuestionWriter` | Draft each question (LLM). |
| `self.critic` | `QualityCritic` | Review each draft (LLM); drives retry/paraphrase. |

There is **no** `if paper_a: … else: skip researcher` (or similar). **`questions_only`**, **`num_slots`**, and **`selected_papers`** only change **flags and data** inside the same `run_pipeline()`; they do **not** remove agents from the graph.

### 1.4 Where each agent is invoked in `run_pipeline`

Typical call sites (same pipeline; repair/regeneration paths also reuse **writer** / **critic** where applicable):

- **`await self.analyst.run()`** — start of pipeline (blueprint).
- **`await self.researcher.run({"query": …})`** — per-slot context before writing.
- **`await self.writer.run(writer_input)`** — per-slot drafting (and paraphrase retries).
- **`await self.critic.run(…)`** — per-slot quality gate.

Grep reference: `self.analyst.run`, `self.researcher.run`, `self.writer.run`, `self.critic.run` in `app/agents/orchestrator.py`.

---

## 2. The five logical roles (orchestrator + four agents)

| # | Role | Implementation | Task (Paper A **and** Paper B) |
|---|------|----------------|--------------------------------|
| 1 | **Orchestrator** | `AgentOrchestrator` (not a `BaseAgent`) | Trim/pad slots, trend loading, template resolution, per-slot loop, validation/repair, normalize, optional strip marks, persist JSON/PDF, checkpoint. |
| 2 | **Blueprint analyst** | `BlueprintAnalyst` | Supplies validated question slots and structure from artifacts. |
| 3 | **Content researcher** | `ContentResearcher` | Retrieves lecture-slide evidence for each slot’s query. |
| 4 | **Question writer** | `QuestionWriter` | Generates question text (and substructure) from template + context. |
| 5 | **Quality critic** | `QualityCritic` | Reviews drafts; failures trigger writer retries. |

### 2.1 Short Notes generation — which agents run

Short Notes (`GET /model-paper/short-notes/{question_no}` in `model_paper.py`) are **outside** `run_pipeline()`. They **do not** use **`AgentOrchestrator`**, **`BlueprintAnalyst`**, **`QuestionWriter`**, or **`QualityCritic`**.

| Component | Short Notes |
|-----------|-------------|
| **`ContentResearcher`** | **Yes** — identical class as in generation: FAISS + MiniLM retrieval; internal **`_summarize_hits`** may run a first LLM call on retrieved chunks. |
| **`QuestionWriter`** | **No** |
| **`QualityCritic`** | **No** |
| **`BlueprintAnalyst`** | **No** |
| **`AgentOrchestrator`** | **No** |
| **FastAPI route + `get_llm_client()`** | **Yes** — second LLM call in `get_short_notes` produces the final markdown short notes (not delegated to Writer). |

Paper A vs Paper B does **not** change Short Notes behaviour (the route only needs `agentic_model_paper.json` + indexed slides). Detail: **`MODEL_PAPER_FRONTEND_AND_SHORT_NOTES.md` §6.0**.

---

## 3. What actually differs between Paper A and Paper B

Only **`options`** and downstream **conditionals** (not “which agents run”):

| Concern | Paper A (typical) | Paper B (typical UI) |
|---------|-------------------|----------------------|
| `num_slots` | Mode from recent papers (1–8) | User 1–8 |
| `selected_papers` | All PDFs in folder | Checked files only |
| `questions_only` | Absent / false → full marks in output, Mongo ±5 marks filter, strict marks validation | Often true → no marks in saved JSON/PDF, no Mongo marks band, relaxed marks validation |
| Trend / `top_topic` | Past-paper blueprints (all listed stems) | **Default:** lecture slides MiniLM + KMeans (`lecture_based_topics`, default true). **Optional:** selected past papers if `lecture_based_topics: false` |

See **`MODEL_PAPER_DEEP_PER_PAPER.md` §1.1** for the full branch table (validation, strip marks, etc.).

---

## 4. End-to-end flow (both papers)

```mermaid
flowchart TB
  subgraph API
    A[POST generate-paper-a]
    B[POST generate-paper]
  end
  subgraph Pipeline["pipeline_service.run_full_pipeline(options)"]
    P1[process_uploaded_files]
    P2[run_agentic_generation(options)]
  end
  subgraph Agentic["AgentOrchestrator.run_pipeline()"]
    AN[BlueprintAnalyst.run]
    TR[Trend / templates / per-slot planning]
    LOOP[For each slot Q1..Qn]
    RS[ContentResearcher.run]
    WR[QuestionWriter.run]
    CR[QualityCritic.run]
    VAL[validate / repair / normalize]
    OUT[JSON + PDF + Mongo]
  end
  A --> Pipeline
  B --> Pipeline
  P1 --> P2
  P2 --> Agentic
  AN --> TR --> LOOP
  LOOP --> RS --> WR --> CR
  CR -->|retry| WR
  LOOP --> VAL --> OUT
```

---

## 5. Summary

- **Yes — verified:** Paper A and Paper B **both** use the **complete** agentic pipeline: **Orchestrator + BlueprintAnalyst + ContentResearcher + QuestionWriter + QualityCritic** for generation.
- Differences are **configuration and post-processing branches** (`options`), not a different set of agents.
- **Short Notes** use **only `ContentResearcher`** among the generation agents, plus a **route-level LLM**; they do **not** use Writer, Critic, Analyst, or the orchestrator (see §2.1).

*Aligned with `model-paper-generation` service layout: `app/api/routes/endpoints/model_paper.py`, `app/services/pipeline_service.py`, `app/agents/orchestrator.py`.*
