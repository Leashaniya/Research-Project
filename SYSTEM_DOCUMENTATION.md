# Research Project - Model Paper Generation System Documentation

## Table of Contents
1. [System Overview](#system-overview)
2. [Technology Stack](#technology-stack)
3. [Paper Generation Process - Step by Step](#paper-generation-process---step-by-step)
4. [Fallback Mechanisms](#fallback-mechanisms)
5. [Retry Logic](#retry-logic)
6. [Architecture Components](#architecture-components)

---

## System Overview

This system is an **AI-powered Model Paper Generation System** that automatically generates university-level exam papers for Database Management Systems courses. The system uses a multi-agent architecture where specialized AI agents collaborate to create authentic, syllabus-aligned exam questions based on past papers and lecture slides.

### Current Implementation Status
- **LLM Provider**: OpenAI GPT-4o-mini (configured via `OPENAI_API_KEY` in `.env` file)
- **Text Analysis**: TF-IDF for semantic similarity in audit reports
- **Planned Updates** (per proposal feedback):
  - Migrate to Google Gemini API (organization provides free API key)
  - Replace TF-IDF with modern embedding-based approaches

### Key Features
- **Multi-Agent Architecture**: Four specialized agents (Analyst, Researcher, Writer, Critic) work together
- **RAG (Retrieval-Augmented Generation)**: Uses lecture slides as context for question generation
- **Template-Based Generation**: Leverages patterns from past papers to ensure authenticity
- **Quality Assurance**: Built-in validation and review mechanisms
- **Checkpoint System**: Resumable generation with progress tracking
- **Fallback Mechanisms**: Multiple layers of fallback to ensure generation completion

---

## Technology Stack

### Core Technologies

#### 1. **LLM (Large Language Model)**
- **Current Implementation**: OpenAI GPT-4o-mini (configured in `.env` file via `OPENAI_API_KEY`)
- **Alternative Support**: Azure OpenAI (if `LLM_PROVIDER=azure` in `.env`)
- **Planned Migration**: Google Gemini API (as per proposal feedback - organization provides free API key)
- **Usage**: Used by Writer and Critic agents for question generation and quality review
- **Configuration**: Set via `OPENAI_API_KEY` and `OPENAI_MODEL` environment variables

#### 2. **Embedding & Semantic Search**
- **Current Implementation**: 
  - `sentence-transformers/all-MiniLM-L6-v2` for embeddings
  - FAISS (Facebook AI Similarity Search) for vector similarity search
- **Planned Update**: Replace TF-IDF with modern embedding-based approaches
- **Usage**: ContentResearcher agent uses this for retrieving relevant lecture slide content

#### 3. **Text Analysis**
- **Current**: TF-IDF (Term Frequency-Inverse Document Frequency) in `audit_report.py`
- **Planned**: Modern approaches like:
  - **KeyBERT** (already partially integrated in `template_analyzer.py`)
  - **BERT-based embeddings** for keyword extraction
  - **Transformer-based topic modeling**

#### 4. **Database**
- **MongoDB**: Stores templates, canonical patterns, and generated papers
- **Collections**:
  - `canonical_templates`: Pre-analyzed question patterns
  - `templates`: Raw question templates from past papers
  - `papers`: Generated model papers

#### 5. **PDF Processing**
- **OCR**: Text extraction from past paper PDFs
- **Image Processing**: Diagram reconstruction from PDF pages
- **Hybrid Extraction**: Combines OCR and direct text extraction

#### 6. **Other Technologies**
- **Python 3.x**: Core language
- **FastAPI**: Backend API framework
- **React**: Frontend (if applicable)
- **JSON**: Data interchange format
- **Mermaid**: Diagram representation format

---

## Paper Generation Process - Step by Step

### Phase 1: Data Preparation (Pre-Generation)

#### Step 1.1: Past Paper Extraction
- **Script**: `backend/scripts/pastpaper_extract.py`
- **Process**:
  1. Load PDF files from `data/past_paper_red_box/`
  2. Extract text using OCR (Optical Character Recognition)
  3. Parse question structures (main questions, sub-questions, marks)
  4. Extract diagrams and convert to Mermaid format
  5. Save structured data to `data/text_extraction_hybrid/{year}/`
  6. Generate `blueprint_with_subquestions.json` for each paper

#### Step 1.2: Lecture Slide Extraction
- **Script**: `backend/scripts/lectureslide_extract.py`
- **Process**:
  1. Extract text from lecture slide PDFs
  2. Chunk slides into manageable segments
  3. Generate embeddings using SentenceTransformer
  4. Build FAISS index for fast similarity search
  5. Save to `data/slides_embeddings/` and `data/lecture_slides_extraction/`

#### Step 1.3: Structure & Template Analysis
- **Script**: `backend/scripts/structure_topics_template.py`
- **Process**:
  1. Analyze all past papers to identify common patterns
  2. Cluster questions by topic and structure
  3. Generate exam blueprint template
  4. Identify high-frequency topics
  5. Save to `data/artifacts/exam_blueprint_template.json`

#### Step 1.4: Canonical Template Generation
- **Script**: `backend/scripts/template_analyzer.py`
- **Process**:
  1. For each question position (Q1, Q2, Q3, etc.):
     - Count topic frequency across all past papers
     - Identify the most frequent topic for that position
     - Select the most recent paper with that topic
     - Extract the exact sub-question structure
  2. Save canonical templates to `data/artifacts/canonical_templates.json`
  3. Sync to MongoDB `canonical_templates` collection

### Phase 2: Agentic Paper Generation

#### Step 2.1: Blueprint Analysis
- **Agent**: `BlueprintAnalyst`
- **Location**: `backend/app/agents/analyst.py`
- **Process**:
  1. Load exam blueprint from `data/artifacts/exam_blueprint_template.json`
  2. Extract exam structure:
     - Exam title
     - Question slots (Q1, Q2, Q3, etc.)
     - Target marks for each slot
     - Suggested topics per slot
  3. **Fallback**: If blueprint missing, use default structure (4 questions, 25 marks each)

#### Step 2.2: Question Generation Loop
For each question slot (Q1, Q2, Q3, ...):

##### Step 2.2.1: Template Selection
- **Location**: `AgentOrchestrator._select_template()` in `orchestrator.py`
- **Process**:
  1. **Primary**: Try to get canonical template from MongoDB for this question position
  2. **Fallback 1**: If no canonical template, query MongoDB `templates` collection:
     - Filter by marks (within ±5 range)
     - Sample 20 candidates
  3. **Syllabus Balancing**: Use `SyllabusClassifier` to:
     - Classify each candidate template into syllabus modules
     - Penalize templates from already-used modules
     - Boost core topics (Normalization, ER Modeling, SQL)
  4. **Fallback 2**: If classifier unavailable, select random candidate
  5. **Fallback 3**: If no candidates, use generic template:
     ```json
     {
       "pattern_label": "General Theory",
       "full_text": "(Reference style only) Explain the concept.",
       "marks": target_marks
     }
     ```
  6. **Template Simplification**: If template has >7 sub-questions, reduce to exactly 7 by merging

##### Step 2.2.2: Context Research
- **Agent**: `ContentResearcher`
- **Location**: `backend/app/agents/researcher.py`
- **Process**:
  1. Build query: `"{exam_title} {topic} {template_pattern_label}"`
  2. Encode query using SentenceTransformer
  3. Search FAISS index for top 5 similar slide chunks
  4. Format results with source information (PDF name, slide number)
  5. Return combined context string

##### Step 2.2.3: Question Writing (with Retry Loop)
- **Agent**: `QuestionWriter`
- **Location**: `backend/app/agents/writer.py`
- **Retry Strategy**: Up to 4 attempts (MAX_RETRIES = 3, so attempts 0-3)
- **Dual-Mode Writing**:
  - **Attempts 0-1**: **Generate Mode** - Pure generation from scratch
  - **Attempts 2-3**: **Paraphrase Mode** - Paraphrase template structure with new scenario

**Generate Mode Process**:
1. Build prompt with:
   - Question metadata (number, marks, topic)
   - Required structure (sub-question breakdown)
   - Lecture slide context
   - Global constraints (used topics, forbidden topics)
   - Mermaid diagram code (if applicable)
2. Call LLM API (currently OpenAI GPT-4o-mini, planned: Gemini)
3. Parse JSON response
4. Validate: Check for empty question text

**Paraphrase Mode Process**:
1. Build prompt with:
   - Reference question from template
   - Instruction to keep structure, change scenario
   - Global uniqueness constraints
   - Mermaid diagram mutation instructions (if applicable)
2. Call LLM API (currently OpenAI GPT-4o-mini, planned: Gemini)
3. Parse JSON response

**Error Handling**:
- If API call fails: Log error, add to feedback, retry
- If JSON parsing fails: Raise exception, retry
- If validation fails (empty text): Raise ValueError, retry

##### Step 2.2.4: Quality Review
- **Agent**: `QualityCritic`
- **Location**: `backend/app/agents/critic.py`
- **Process**:

**Deterministic Checks (No LLM, Immediate Rejection)**:
1. **Math Check**: Sub-question marks must sum to total marks
2. **Structure Check**: Number of sub-questions must match template structure
3. **Hallucination Check**: Reject if contains:
   - `[figure:`, `slide_`, `fig_`, `page_`, `refer to`, `diagram above`
   - Exception: `[PLACEHOLDER FIGURE]` is allowed
4. **Content Quality Checks**:
   - Text length must be ≥10 characters
   - No vague/subjective questions ("think of", "your opinion")
   - If asks to analyze/normalize, must provide relation schema
   - Mark-to-effort mismatch check (e.g., 1 mark for 100+ word question)
   - Database Systems relevance check (reject networking, OS, etc.)
   - Scenario repetition check (same text in multiple sub-questions)

**LLM-Based Review**:
1. If passes deterministic checks, send to LLM for:
   - Content relevance verification
   - Hallucination detection
   - Scenario completeness check
2. LLM returns: `{"approved": true/false, "feedback": "..."}`

**Fallback**: If LLM review fails, auto-approve with warning

##### Step 2.2.5: Retry Decision
- **If Approved**: 
  - Normalize labels (a, b, c, ...)
  - Update global tracking (used topics, scenarios, question types)
  - Save to checkpoint
  - Move to next question

- **If Rejected**:
  - **Attempt 0-1**: Retry with feedback
  - **Attempt 2-3**: Switch to paraphrase mode, retry
  - **After Max Retries**: Force approval with fallback (see Fallback Mechanisms)

##### Step 2.2.6: Checkpoint Saving
- **Location**: `data/outputs/model_papers/generation_checkpoint.json`
- **Process**: After each approved question, save all completed questions
- **Purpose**: Enable resumable generation if process interrupted

#### Step 2.3: Post-Generation Validation
- **Function**: `AgentOrchestrator._validate_topic_coverage()`
- **Checks**:
  1. No single topic dominates (>40% of total marks)
  2. Minimum topic diversity (at least 3 distinct topics for 5+ questions)
  3. Logs warnings if validation fails

#### Step 2.4: Final Output Generation
1. **JSON Export**: Save to `data/outputs/model_papers/agentic_model_paper.json`
2. **MongoDB Save**: Insert into `papers` collection
3. **PDF Export**: Generate PDF using `PDFService.generate_pdf()`
4. **Checkpoint Cleanup**: Delete checkpoint file

---

## Fallback Mechanisms

### Overview
The system implements **multi-layered fallback mechanisms** to ensure paper generation completes even when primary methods fail. Fallbacks are designed to maintain quality while guaranteeing completion.

### Fallback Hierarchy

#### Level 1: Template Selection Fallbacks

**When**: No canonical template found for question position

**Fallback Chain**:
1. **Primary**: Query MongoDB `canonical_templates` collection by `position_id`
2. **Fallback 1**: Query MongoDB `templates` collection with mark-based filtering
3. **Fallback 2**: If classifier unavailable, select random candidate
4. **Fallback 3**: Use generic template:
   ```python
   {
       "pattern_label": "General Theory",
       "full_text": "(Reference style only) Explain the concept.",
       "marks": target_marks
   }
   ```

**Why**: Ensures every question slot gets a template, even if database is incomplete

**Location**: `orchestrator.py` lines 104-186

---

#### Level 2: Writer Mode Fallback

**When**: Generate mode fails after 2 attempts

**Fallback**: Switch from **Generate Mode** to **Paraphrase Mode**

**How**:
- Attempts 0-1: Use `_build_generation_prompt()` (pure generation)
- Attempts 2-3: Use `_build_paraphrase_prompt()` (template-based paraphrasing)

**Why**: 
- Generate mode is more creative but can fail quality checks
- Paraphrase mode is safer, guaranteed to follow template structure
- Reduces hallucination risk

**Location**: `orchestrator.py` lines 432-438

---

#### Level 3: Math Error Immediate Fallback

**When**: Critic detects MATH ERROR (marks don't sum correctly)

**Fallback**: Skip remaining retries, immediately apply **Strict Template Fallback**

**Why**: Math errors are deterministic and won't be fixed by retrying. Immediate fallback saves API calls.

**Location**: `orchestrator.py` lines 515-518

---

#### Level 4: Quality Error Fallback

**When**: Question fails quality checks after all retries

**Fallback Process**:

1. **Sanitization** (if QUALITY ERROR):
   - Remove hallucination placeholders: `[FIGURE: ...]`, `slide 22`, `fig 1`
   - Replace with: `"(Diagram omitted - please refer to context)"`

2. **Strict Template Fallback**:
   - Extract structure from template (`required_structure` or `subquestions`)
   - Create fallback draft matching template exactly:
     ```python
     fallback_draft = {
         "question_no": q_no,
         "marks": target_marks,
         "subquestions": []
     }
     ```
   - For each template item:
     - Scale marks if template total ≠ target marks
     - Salvage text from failed draft (if available)
     - If no salvaged text or too short, generate context-aware fallback:
       - **ER Diagram**: "Construct an ER/EER diagram for the scenario..."
       - **Normalization**: "Normalize the given relation schema..."
       - **SQL Query**: "Write the SQL query to retrieve..."
       - **General**: "Define and explain the key concepts..."
   - Fix rounding errors (distribute remainder to highest-mark item)
   - Inject diagram from cache if applicable

3. **Diagram Injection** (if ER/Diagram question):
   - Search pre-processed diagram cache
   - Match by pattern label
   - Inject Mermaid code into draft

**Why**: 
- Ensures mathematical correctness (marks always sum correctly)
- Maintains structure authenticity (follows real past paper patterns)
- Guarantees completion (never leaves empty questions)

**Location**: `orchestrator.py` lines 520-641

---

#### Level 5: Blueprint Fallback

**When**: Exam blueprint file not found

**Fallback**: Use default blueprint:
```python
{
    "exam_title": "Model Exam (Fallback)",
    "question_slots": [
        {"question_no": "Q1", "target_marks": 25, "topics": ["General"]},
        {"question_no": "Q2", "target_marks": 25, "topics": ["General"]},
        {"question_no": "Q3", "target_marks": 25, "topics": ["General"]},
        {"question_no": "Q4", "target_marks": 25, "topics": ["General"]},
    ]
}
```

**Why**: Allows generation to proceed even if structure analysis hasn't run

**Location**: `analyst.py` lines 41-52

---

#### Level 6: LLM API Fallback

**When**: LLM API call fails (network error, rate limit, etc.)

**Writer Agent**:
- Logs error
- Adds error to feedback
- Retries (up to MAX_RETRIES)

**Critic Agent**:
- If LLM review fails: Auto-approve with warning
- Log: `"Critic failure ({e}), auto-approved."`

**Why**: Prevents pipeline from halting due to transient API issues (network errors, rate limits, etc.)

**Note**: Currently uses OpenAI GPT API. When migrated to Gemini, same retry logic applies.

**Location**: 
- `writer.py` lines 74-76
- `critic.py` lines 162-164

---

#### Level 7: Resource Loading Fallbacks

**ContentResearcher**:
- If FAISS index missing: Raises exception (intentional, requires pre-processing)
- If chunks file missing: Raises exception

**SyllabusClassifier**:
- If SentenceTransformer fails to load: `self.classifier = None`
- Template selection falls back to random selection

**Why**: Graceful degradation when optional components unavailable

**Location**: 
- `researcher.py` lines 27-47
- `orchestrator.py` lines 93-98, 184-186

---

### Fallback Summary Table

| Level | Trigger | Fallback Action | Location |
|-------|---------|----------------|----------|
| 1 | No canonical template | Query templates → Random → Generic | `orchestrator.py:104-186` |
| 2 | Generate mode fails (2 attempts) | Switch to paraphrase mode | `orchestrator.py:432-438` |
| 3 | Math error detected | Immediate template fallback | `orchestrator.py:515-518` |
| 4 | Quality error after max retries | Sanitize + strict template fallback | `orchestrator.py:520-641` |
| 5 | Blueprint missing | Use default blueprint | `analyst.py:41-52` |
| 6 | LLM API failure | Retry → Auto-approve (critic) | `writer.py:74-76`, `critic.py:162-164` |
| 7 | Resource loading failure | Disable feature, use alternative | `researcher.py:27-47`, `orchestrator.py:93-98` |

---

## Retry Logic

### Overview
The system implements **intelligent retry logic** with multiple strategies to handle transient failures and quality issues.

### Retry Configuration

```python
MAX_RETRIES = 3  # Defined in orchestrator.py line 11
```

This means **4 total attempts** (attempts 0, 1, 2, 3).

---

### Retry Scenarios

#### Scenario 1: Writer API Failure

**Trigger**: Exception during LLM API call or JSON parsing

**Retry Logic**:
```python
for attempt in range(MAX_RETRIES + 1):  # 0, 1, 2, 3
    try:
        draft = await self.writer.run({...})
        # ... continue to critic
    except Exception as e:
        print(f"⚠️ Writer failed on attempt {attempt}: {e}. Retrying...")
        feedback = f"Previous generation failed with error: {e}. Ensure all fields are filled."
        continue  # Retry
```

**Behavior**:
- Retries up to 4 times
- Each retry includes error message in feedback
- After max retries, falls back to template-based generation

**Location**: `orchestrator.py` lines 432-458

---

#### Scenario 2: Quality Rejection (Normal Flow)

**Trigger**: Critic rejects draft (quality issues, hallucinations, etc.)

**Retry Logic**:
```python
for attempt in range(MAX_RETRIES + 1):
    # ... writer generates draft
    review = await self.critic.run({...})
    is_approved = review.get("approved", True)
    
    if is_approved:
        approved = True
        break  # Success, exit retry loop
    else:
        feedback = review.get("feedback", "No feedback")
        # Continue to next attempt with feedback
```

**Behavior**:
- Attempts 0-1: Generate mode with feedback
- Attempts 2-3: Paraphrase mode with feedback
- After max retries: Force approval with fallback

**Location**: `orchestrator.py` lines 460-518

---

#### Scenario 3: Math Error (Immediate Fallback)

**Trigger**: Critic detects marks don't sum correctly

**Retry Logic**:
```python
if "MATH ERROR" in feedback.upper():
    print(f"🛑 Math mismatch detected. Skipping retries and applying fallback logic.")
    break  # Exit retry loop immediately
```

**Behavior**:
- **No retries** - Math errors are deterministic
- Immediately applies strict template fallback
- Saves API calls and time

**Why**: Math errors won't be fixed by retrying; template fallback ensures correctness

**Location**: `orchestrator.py` lines 515-518

---

#### Scenario 4: Mode Switching (Dual-Mode Retry)

**Trigger**: Generate mode fails quality checks

**Retry Logic**:
```python
writer_mode = "generate"
if attempt >= 2:
    writer_mode = "paraphrase"

draft = await self.writer.run({
    ...,
    "mode": writer_mode
})
```

**Behavior**:
- **Attempts 0-1**: Generate mode (creative, original)
- **Attempts 2-3**: Paraphrase mode (safe, structured)
- Each mode uses different prompt strategy

**Why**: 
- Generate mode: Higher quality when successful, but can hallucinate
- Paraphrase mode: More reliable, follows template structure exactly

**Location**: `orchestrator.py` lines 433-438

---

### Retry Flow Diagram

```
Question Generation Start
    ↓
Attempt 0 (Generate Mode)
    ↓
[Writer] → [Critic]
    ↓
Approved? ──Yes──→ Save & Continue
    ↓ No
Feedback collected
    ↓
Attempt 1 (Generate Mode)
    ↓
[Writer] → [Critic]
    ↓
Approved? ──Yes──→ Save & Continue
    ↓ No
Feedback collected
    ↓
Attempt 2 (Paraphrase Mode) ← Mode Switch
    ↓
[Writer] → [Critic]
    ↓
Approved? ──Yes──→ Save & Continue
    ↓ No
Feedback collected
    ↓
Attempt 3 (Paraphrase Mode)
    ↓
[Writer] → [Critic]
    ↓
Approved? ──Yes──→ Save & Continue
    ↓ No
Math Error? ──Yes──→ Immediate Template Fallback
    ↓ No
Apply Strict Template Fallback
    ↓
Force Approval & Save
```

---

### Retry Parameters Summary

| Parameter | Value | Purpose |
|-----------|-------|---------|
| `MAX_RETRIES` | 3 | Maximum retry attempts (4 total attempts) |
| Generate Mode Attempts | 0-1 | First 2 attempts use creative generation |
| Paraphrase Mode Attempts | 2-3 | Last 2 attempts use template paraphrasing |
| Math Error Retries | 0 | Immediate fallback (no retries) |
| API Failure Retries | 0-3 | Retry on transient errors |

---

## Architecture Components

### Agent System

#### 1. BlueprintAnalyst
- **Role**: Exam structure planner
- **Input**: None (loads from file)
- **Output**: Exam blueprint (slots, marks, topics)
- **Fallback**: Default blueprint if file missing

#### 2. ContentResearcher
- **Role**: Context librarian
- **Input**: Query string
- **Output**: Relevant lecture slide chunks
- **Technology**: FAISS + SentenceTransformer
- **Fallback**: Raises exception (requires pre-processing)

#### 3. QuestionWriter
- **Role**: Question setter
- **Input**: Slot, template, context, feedback, mode
- **Output**: Draft question JSON
- **Technology**: OpenAI GPT-4o-mini (current), Gemini (planned)
- **Modes**: Generate, Paraphrase
- **Fallback**: Retry with error feedback

#### 4. QualityCritic
- **Role**: Quality reviewer
- **Input**: Draft, context, template
- **Output**: Approval status + feedback
- **Technology**: Deterministic checks + LLM review
- **Fallback**: Auto-approve if LLM fails

### Orchestrator
- **Role**: Workflow coordinator
- **Responsibilities**:
  - Manages agent interactions
  - Implements retry logic
  - Applies fallback mechanisms
  - Saves checkpoints
  - Validates topic coverage

### Supporting Systems

#### SyllabusClassifier
- **Technology**: SentenceTransformer (`all-MiniLM-L6-v2`)
- **Purpose**: Classify templates into syllabus modules
- **Modules**: ER Modeling, Normalization, SQL, Transactions, Indexing, Advanced

#### PDFService
- **Purpose**: Generate PDF from JSON paper
- **Output**: Formatted exam paper PDF

#### MongoDB Integration
- **Collections**:
  - `canonical_templates`: Pre-analyzed question patterns
  - `templates`: Raw question templates
  - `papers`: Generated papers

---

## Current Implementation Notes

### Technologies to Update (Per Proposal Feedback)

1. **TF-IDF Replacement**:
   - **Current**: Used in `audit_report.py` for semantic similarity
   - **Planned**: Replace with modern embedding-based approaches
   - **Options**: 
     - SentenceTransformer embeddings + cosine similarity
     - BERT-based keyword extraction
     - KeyBERT (already partially integrated)

2. **GPT to Gemini Migration**:
   - **Current**: OpenAI GPT-4o-mini (configured via `OPENAI_API_KEY` in `.env`)
   - **Planned**: Google Gemini API (organization provides free API key)
   - **Configuration**: 
     - Current: `OPENAI_API_KEY` and `OPENAI_MODEL` in `.env`
     - Planned: `GOOGLE_API_KEY` and `GEMINI_MODEL` in `.env` (already defined in `config.py`)
   - **Files to Update**:
     - `llm_factory.py`: Add Gemini client initialization
     - `writer.py`: Update to use Gemini model when `LLM_PROVIDER=gemini`
     - `critic.py`: Update to use Gemini model when `LLM_PROVIDER=gemini`
   - **Note**: System currently uses GPT as configured in environment variables

---

## Conclusion

This system implements a robust, multi-layered approach to automated exam paper generation with:
- **Intelligent retry logic** (4 attempts with mode switching)
- **Comprehensive fallback mechanisms** (7 levels of fallback)
- **Quality assurance** (deterministic + LLM-based validation)
- **Resumable generation** (checkpoint system)
- **Syllabus alignment** (module balancing, topic diversity)

The architecture ensures that paper generation **always completes**, even when individual components fail, while maintaining quality through multiple validation layers.

