# Model Paper Generation - Complete Step-by-Step Documentation

## Table of Contents
1. [Overview](#overview)
2. [System Architecture](#system-architecture)
3. [Phase 1: Preprocessing Pipeline](#phase-1-preprocessing-pipeline)
4. [Phase 2: Agentic Pipeline](#phase-2-agentic-pipeline)
5. [Phase 3: Model Paper Generation](#phase-3-model-paper-generation)
6. [DALL·E Image Generation Integration](#dall·e-image-generation-integration)
7. [Data Flow Diagram](#data-flow-diagram)
8. [Key Components Deep Dive](#key-components-deep-dive)
9. [Error Handling & Fallbacks](#error-handling--fallbacks)

---

## Overview

This system is an **AI-powered Model Paper Generation System** that automatically generates university-level exam papers for Database Management Systems courses. The system follows a two-phase approach:

1. **Preprocessing Phase**: Extracts and analyzes past papers and lecture slides to build knowledge bases
2. **Agentic Pipeline Phase**: Uses specialized AI agents to generate new exam questions following authentic patterns

The final output is a complete model exam paper in both JSON and PDF formats.

---

## System Architecture

### High-Level Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    PREPROCESSING PHASE                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│  │ Past Paper   │  │ Lecture Slide│  │ Structure &  │        │
│  │ Extraction   │  │ Extraction    │  │ Template     │        │
│  │              │  │              │  │ Analysis     │        │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘        │
│         │                  │                  │                  │
│         └──────────────────┴──────────────────┘                  │
│                            │                                     │
│                            ▼                                     │
│              ┌─────────────────────────┐                        │
│              │  Knowledge Base Ready    │                        │
│              │  - Blueprints            │                        │
│              │  - Templates            │                        │
│              │  - Embeddings           │                        │
│              │  - Diagrams              │                        │
│              └─────────────┬───────────┘                        │
└────────────────────────────┼────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    AGENTIC PIPELINE PHASE                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│  │ Blueprint    │  │ Content      │  │ Question     │        │
│  │ Analyst      │  │ Researcher   │  │ Writer       │        │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘        │
│         │                  │                  │                  │
│         └──────────────────┴──────────────────┘                  │
│                            │                                     │
│                            ▼                                     │
│              ┌─────────────────────────┐                        │
│              │  Quality Critic         │                        │
│              │  (Review & Validation)   │                        │
│              └─────────────┬───────────┘                        │
│                            │                                     │
│                            ▼                                     │
│              ┌─────────────────────────┐                        │
│              │  Model Paper Generated  │                        │
│              │  (JSON + PDF)          │                        │
│              └─────────────────────────┘                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## Phase 1: Preprocessing Pipeline

The preprocessing phase prepares all necessary data structures and knowledge bases that the agentic pipeline will use. This phase runs **once** before generation begins.

### Step 1.1: Past Paper Extraction

**Script**: `backend/scripts/pastpaper_extract.py`

**Purpose**: Extract structured data from past exam paper PDFs

**Input**: 
- PDF files from `data/past_paper_red_box/*.pdf`

**Process**:

1. **PDF Rendering**
   - Converts each PDF page to PNG images using PyMuPDF (no Poppler required)
   - Uses 300 DPI for standard quality, 600 DPI fallback for low-confidence pages
   - Saves temporary page images to `data/_tmp_pdf_pages_hybrid/`

2. **Red Box Detection** (Diagram Extraction)
   - Uses OpenCV to detect red-bordered boxes in images (HSV color space)
   - These boxes typically contain diagrams (ER diagrams, schemas, etc.)
   - Extracts diagram regions and saves as separate PNG files
   - Creates thumbnails for quick preview

3. **Text Extraction** (Hybrid Approach)
   - **Primary**: Extracts text directly from PDF text layer (if available)
   - **Fallback**: Uses Tesseract OCR for scanned pages
   - **Smart Filtering**: Excludes text that overlaps with diagram regions
   - **Deskewing**: Automatically corrects page rotation if detected

4. **Diagram Analysis** (Cloud AI - Optional)
   - If `USE_CLOUD_AI = True`, analyzes each extracted diagram using Vision AI
   - Extracts semantic labels (e.g., "ER Diagram", "Normalization Schema")
   - Identifies student actions required (e.g., "Draw", "Normalize")
   - Saves metadata to `diagrams_metadata.jsonl`

5. **Blueprint Parsing**
   - **Primary Method**: Uses Cloud AI (`analyze_document_structure`) to extract:
     - Question numbers (Q1, Q2, Q3, etc.)
     - Total marks per question
     - Sub-question structure (a, b, c, etc.)
     - Sub-question marks
   - **Fallback Method**: Regex-based parsing if AI fails:
     - Detects question headers (e.g., "Question 1", "Q1:")
     - Extracts marks from patterns like "(25 marks)"
     - Parses sub-questions using label patterns (a), b), i., etc.)

6. **Output Generation**
   - Saves per-PDF outputs to `data/text_extraction_hybrid/{pdf_stem}/`:
     - `pages_text/page_XXX_text.txt` - Text from each page
     - `diagrams/page_XXX_diagram_N.png` - Extracted diagrams
     - `all_text_with_diagrams.txt` - Combined text with diagram placeholders
     - `cleaned_document.txt` - Cleaned full document
     - `blueprint.json` - Main questions only
     - `blueprint_with_subquestions.json` - Full structure with sub-questions
   - Generates global outputs:
     - `chunks.jsonl` - Text chunks for indexing
     - `chunks_index.csv` - Chunk metadata
     - `diagrams_manifest.json` - Diagram inventory

7. **Quality Control**
   - Runs OCR confidence checks
   - Flags low-confidence pages (< 60% confidence)
   - Auto-retries low-confidence pages at higher DPI (600 DPI)
   - Generates QC report: `ocr_qc_report/ocr_conf_report.json`

**Key Outputs**:
- Structured question blueprints for each past paper
- Extracted diagrams with metadata
- Text chunks ready for embedding

---

### Step 1.2: Lecture Slide Extraction

**Script**: `backend/scripts/lectureslide_extract.py`

**Purpose**: Extract and index lecture slide content for RAG (Retrieval-Augmented Generation)

**Input**:
- PDF files from `data/lectureslides/*.pdf`

**Note on Diagram Handling**: 
- **Lecture Slides**: Vision AI extracts **captions and descriptions** for semantic search to make diagrams searchable in the RAG system.
- **Exam Papers** (Step 1.1): Diagrams are extracted for potential reuse in generated questions, with semantic labels for matching.

**Process**:

1. **PDF Processing**
   - Renders each slide to PNG (220 DPI)
   - Detects green-bordered boxes (figures/diagrams in slides)
   - Extracts text from PDF text layer (primary) or OCR (fallback)

2. **Figure Extraction**
   - Extracts green-boxed figures as separate images
   - Analyzes figures using Cloud AI Vision Model (GPT-4o-mini with vision capabilities) if `USE_CLOUD_AI = True`:
     - **Purpose**: Extracts detailed captions and descriptions from diagrams
       - Uses Vision AI to understand diagram content
       - Generates dense, searchable textual descriptions optimized for semantic search
       - Captures concepts, relationships, and key information shown in the diagram
   - Saves figure metadata to `figures_metadata.jsonl`:
     - `caption`: Detailed textual description (used for RAG/search)

3. **Text Chunking**
   - Splits slide text into overlapping chunks:
     - Chunk size: 350 words
     - Overlap: 70 words
   - Injects figure metadata into chunks containing `[FIGURE: ...]` tags
   - **Enriches chunks with semantic descriptions from Vision AI analysis**:
     - **Caption**: Detailed textual description is injected into chunks for semantic search
     - This enrichment makes diagrams searchable via FAISS - when a question asks about a concept shown in a diagram, the caption helps retrieve that chunk

4. **Embedding Generation**
   - Uses SentenceTransformer model: `all-MiniLM-L6-v2`
   - Encodes all chunks into 384-dimensional vectors
   - Normalizes embeddings (L2 normalization)

5. **FAISS Index Building**
   - Creates FAISS IndexFlatIP (Inner Product) index
   - Adds all embeddings to index
   - Enables fast similarity search (sub-millisecond retrieval)

**Key Outputs**:
- `data/lecture_slides_extraction/slides_chunks.jsonl` - All slide chunks (enriched with figure captions)
- `data/slides_embeddings/slides_embeddings.npy` - Embedding vectors
- `data/slides_embeddings/slides_faiss_index_flatip.index` - Search index
- `data/slides_embeddings/slides_metadata.jsonl` - Chunk metadata
- `data/lecture_slides_extraction/{pdf_stem}/figures_metadata.jsonl` - Figure metadata (captions)

**Why This Matters**: 
- **Caption Extraction**: The Vision AI extracts detailed captions that describe diagram content. These captions are injected into text chunks, making diagrams searchable via semantic search. When generating questions about concepts shown in diagrams, the system can retrieve relevant slide content.
- The agentic pipeline uses this index to retrieve relevant lecture content when generating questions, ensuring syllabus alignment.

---

### Step 1.3: Structure & Template Analysis

**Script**: `backend/scripts/structure_topics_template.py`

**Purpose**: Analyze all past papers to discover patterns and create exam blueprint

**Input**:
- All `blueprint_with_subquestions.json` files from Step 1.1

**Process**:

1. **Paper Filtering**
   - Filters "good papers" (total marks = 100, no missing marks)
   - **Selects latest 6 papers for blueprint construction** (used for structural analysis)
   - Uses all good papers for topic clustering (broader dataset for topic discovery)

2. **Exam Structure Template (Empirical Marking Template)**
   - **ENFORCED**: Always generates exactly 4 questions (Q1-Q4) regardless of historical paper counts
   - **ENFORCED**: Canonical total marks = 100 (distributed across 4 slots)
   - Analyzes question positions from latest 6 papers:
     - Position 1 (Q1), Position 2 (Q2), Position 3 (Q3), Position 4 (Q4)
     - **Note**: If historical papers have Q5, Q6, etc., those positions are analyzed for topic frequency but NOT included in final blueprint
     - Target marks per position (median of historical values from Q1-Q4 positions)
     - Typical number of sub-questions per position
     - **Structural Fingerprint**: Most common sub-question mark distribution
   - Creates blueprint with:
     - `canonical_num_questions`: **Always 4** (hardcoded, not derived from mode)
     - `canonical_total_marks`: **Always 100**
     - `question_slots`: Exactly 4 slots (Q1-Q4), each with:
       - `target_marks`: Median marks for this position
       - `typical_num_subquestions`: Most common sub-question count
       - `structural_fingerprint`: Modal sub-question mark split (e.g., [5, 5, 5, 5, 5] for 25 marks)

3. **Topic Discovery (K-Means Clustering)**
   - **Vectorization**: Encodes all question texts using SentenceTransformer
   - **Clustering**: Runs K-Means (k=7) to group similar questions
   - **Topic Labeling**: Extracts representative keywords from each cluster
   - **Topic Frequency Analysis (Across ALL Positions)**:
     - **Analyzes ALL question positions (Q1, Q2, Q3, Q4, Q5, Q6, etc.) from latest 6 papers**
     - Calculates topic frequency across ALL positions (not just Q1-Q4)
     - **Most Frequent Topic**: Identifies the single most frequent topic across all positions
     - **Forced Assignment**: Most frequent topic is forced into Q1 slot
   - **Position-Topic Correlation (for Q2-Q4)**:
     - For each position (Q2, Q3, Q4), finds most common topic for that specific position
     - Ensures unique topics across Q1-Q4 (no duplicates)
     - Topic probability distribution shows how often each topic appears at each position

4. **Template Question Selection**
   - Selects representative questions from each cluster
   - Prioritizes longer, more detailed questions
   - Ensures position diversity (samples from Q1-Q5+ for analysis, but templates are used for Q1-Q4 generation)
   - **Topic Frequency Consideration**: Templates are selected based on topic frequency from latest 6 papers
   - **Syllabus Alignment**: Ensures templates align with core exam topics
   - Classifies each template by pattern:
     - `RELATIONAL_ALGEBRA`
     - `NORMALIZATION_FD_KEYS`
     - `ER_EER_MODELING`
     - `SQL_DDL_DML`
     - `TRANSACTIONS_CONCURRENCY`
     - `INDEXING_STORAGE`
     - `GENERAL_THEORY`

**Key Outputs**:
- `data/artifacts/exam_blueprint_template.json` - Exam structure blueprint
- `data/artifacts/topic_assignments.json` - Question-to-cluster mappings
- `data/artifacts/high_frequency_topics.json` - Top 7 topic clusters
- `data/artifacts/template_questions.json` - Representative question templates

**Example Blueprint Structure**:
```json
{
  "canonical_num_questions": 4,
  "canonical_total_marks": 100,
  "question_slots": [
    {
      "slot_id": "Q1",
      "position": 1,
      "target_marks": 25,
      "typical_num_subquestions": 5,
      "structural_fingerprint": [5, 5, 5, 5, 5],
      "topics": ["ER Modeling", "Entity Relationship"],
      "forced_topic": true,
      "topic_source": "most_frequent_across_all_positions",
      "topic_probabilities": {
        "ER Modeling": 0.60,
        "SQL Queries": 0.30,
        "General Theory": 0.10
      }
    },
    {
      "slot_id": "Q2",
      "position": 2,
      "target_marks": 25,
      "topics": ["Normalization", "Functional Dependencies"],
      "forced_topic": false,
      "topic_source": "position_2_most_common"
    },
    ...
  ]
}
```

**Key Points**:
- Q1 always has `forced_topic: true` with the most frequent topic across ALL positions
- Q2-Q4 have unique topics (enforced through cluster filtering)
- Total marks always sum to 100 across 4 slots

---

### Step 1.4: Canonical Template Generation

**Script**: `backend/scripts/template_analyzer.py`

**Purpose**: Create canonical templates for each question position based on frequency analysis

**Input**:
- `data/artifacts/template_questions.json` from Step 1.3

**Process**:

1. **Position Grouping**
   - Groups all templates by question position (Q1, Q2, Q3, etc.)

2. **Topic Frequency Analysis**
   - For each position, counts topic frequency using cluster keywords
   - Identifies dominant topic (most frequent)

3. **Most Recent Paper Selection**
   - Finds most recent paper containing the dominant topic at this position
   - Extracts exact sub-question structure from that paper

4. **Structure Extraction**
   - Extracts sub-question labels (a, b, c, etc.)
   - Extracts marks per sub-question
   - Determines question type from text (List, Define, Draw, Calculate, etc.)

5. **Topic Name Conversion**
   - Uses KeyBERT (if available) or heuristics to convert keywords to readable topic names
   - Examples:
     - Keywords: ["er", "diagram", "entity"] → "ER and EER Diagrams"
     - Keywords: ["normalization", "functional", "dependency"] → "Functional Dependencies and Normalization"

6. **MongoDB Sync**
   - Saves canonical templates to MongoDB `canonical_templates` collection
   - Each template has:
     - `position_id`: "Q1", "Q2", etc.
     - `dominant_topic`: Human-readable topic name
     - `source_paper`: Year of source paper
     - `total_marks`: Total marks for this question
     - `subquestion_structure`: Exact sub-question breakdown

**Key Outputs**:
- `data/artifacts/canonical_templates.json` - Canonical templates per position
- MongoDB `canonical_templates` collection (synced)

**Example Canonical Template**:
```json
{
  "Q1": {
    "dominant_topic": "ER and EER Diagrams",
    "source_paper": "2024 II",
    "total_marks": 25,
    "subquestion_count": 5,
    "subquestion_structure": [
      {"label": "a", "marks": 5, "type": "List"},
      {"label": "b", "marks": 5, "type": "Draw"},
      {"label": "c", "marks": 5, "type": "Explain"},
      {"label": "d", "marks": 5, "type": "Map"},
      {"label": "e", "marks": 5, "type": "Describe"}
    ]
  }
}
```

**Why This Matters**: The agentic pipeline uses canonical templates to ensure generated questions follow authentic past-paper patterns.

---

## Phase 2: Agentic Pipeline

The agentic pipeline uses specialized AI agents to generate new exam questions. This phase runs **on-demand** when a model paper is requested.

### Entry Point

**Script**: `run_agentic.py` or `backend/app/agents/orchestrator.py`

**Orchestrator**: `AgentOrchestrator` class manages the entire pipeline

---

### Step 2.1: Blueprint Analysis

**Agent**: `BlueprintAnalyst` (`backend/app/agents/analyst.py`)

**Purpose**: Load and validate the exam blueprint

**Process**:

1. **Blueprint Loading**
   - Loads `data/artifacts/exam_blueprint_template.json`
   - **ENFORCES**: Exactly 4 slots (Q1-Q4) - limits to first 4 if blueprint has more
   - Validates structure integrity:
     - **Exactly 4 slots required** (hard limit)
     - All slots have valid marks (> 0)
     - Total marks reconciliation (ensures sum = 100)

2. **Structure Repair** (if needed)
   - If marks are missing/invalid:
     - Uses `canonical_total_marks` (100) / 4 for even distribution (25 marks each)
     - Or uses average from valid slots
     - Or uses configurable default (not tied to question number)
   - Ensures all slots have valid IDs (Q1, Q2, Q3, Q4)

3. **Fallback**
   - If blueprint file missing, returns default blueprint:
     - **Exactly 4 questions**, 25 marks each (total = 100)
     - Generic topics

**Output**: Validated blueprint dictionary with exactly 4 question slots (Q1-Q4)

**Key Principles**: 
- **GOLDEN RULE**: Question number never decides topic. Topics emerge from past-paper data analysis, not position.
- **ENFORCEMENT**: Final model paper always contains exactly 4 questions (Q1-Q4), regardless of historical paper structure.
- **TOPIC FREQUENCY**: Most frequent topic (across ALL positions Q1-Q5+) is forced into Q1.

---

### Step 2.2: Question Generation Loop

For each question slot in the blueprint, the orchestrator runs the following sub-steps:

#### Step 2.2.1: Template Selection

**Location**: `AgentOrchestrator._select_template()`

**Purpose**: Select the best template for this question slot

**Process**:

1. **Canonical Template Retrieval** (Primary)
   - Queries MongoDB `canonical_templates` collection by `position_id`
   - If found, uses canonical template (most frequent topic + structure for this position)
   - **Note**: Templates are based on topic frequency analysis from latest 6 papers

2. **Smart Template Selection** (Fallback)
   - If no canonical template:
     - Queries MongoDB `templates` collection
     - Filters by marks (within ±5 range)
     - Samples 30 candidates
     - **Topic Frequency & Syllabus Balancing**:
       - Templates are selected by balancing topic frequency across latest 6 papers
       - Uses `SyllabusClassifier` to classify each candidate into modules:
         - "Introduction & ER Modeling"
         - "Relational Model & Normalization"
         - "SQL & Queries"
         - "Transactions & Concurrency"
         - "Indexing & Storage"
         - "Advanced & Other"
       - Penalizes templates from already-used modules (-50 points)
       - Boosts core topics (+10 points)
     - **Diversity Enforcement**:
       - Penalizes already-used template IDs (-1000 points)
       - Penalizes already-used intents/patterns (-50 points)
       - **Penalizes banned topics** (topics already used in previous questions) (-100 points)
       - Bonuses unused intents (+30 points)
     - Selects highest-scoring candidate

3. **Generic Template** (Last Resort)
   - If no candidates found, uses generic template:
     ```json
     {
       "pattern_label": "General Theory",
       "full_text": "(Reference style only) Explain the concept.",
       "marks": target_marks
     }
     ```

4. **Template Simplification**
   - If template has >7 sub-questions, reduces to exactly 7
   - Merges small questions to maintain mark total

**Output**: Selected template dictionary with structure and pattern label

**Key Points**:
- Template selection considers topic frequency from latest 6 papers
- Banned topics (already used) are penalized to ensure uniqueness
- Syllabus alignment ensures core topics are prioritized

---

#### Step 2.2.2: Context Research

**Agent**: `ContentResearcher` (`backend/app/agents/researcher.py`)

**Purpose**: Retrieve relevant lecture slide content for question generation

**Process**:

1. **Query Construction**
   - Builds query: `"{exam_title} {topic} {template_pattern_label}"`
   - Example: "Database Management Systems ER Modeling ER_EER_MODELING"

2. **Semantic Search**
   - Encodes query using SentenceTransformer (`all-MiniLM-L6-v2`)
   - Searches FAISS index for top 5 similar chunks
   - Retrieves chunk texts with source information

3. **LLM Summarization** (Optional)
   - Uses LLM to extract key facts from retrieved chunks
   - Formats as structured evidence:
     - Key Facts (bullet points)
     - Key Terms
     - Diagrams (if mentioned)

**Output**: Context string with relevant lecture slide content

**Why This Matters**: Ensures generated questions align with syllabus content taught in lectures.

---

#### Step 2.2.3: Question Writing

**Agent**: `QuestionWriter` (`backend/app/agents/writer.py`)

**Purpose**: Generate draft question using LLM

**Modes**:
- **Generate Mode** (Attempts 0-1): Pure generation from scratch
- **Paraphrase Mode** (Attempts 2-3): Paraphrase template structure with new scenario

**Process**:

1. **Prompt Construction**
   - **Generate Mode**:
     - Includes question metadata (number, marks, topic)
     - Required structure (sub-question breakdown)
     - Lecture slide context
     - Global constraints (used topics, forbidden topics)
     - Anti-repetition rules
     - Diagram generation instructions (if needed)
   - **Paraphrase Mode**:
     - Includes reference question from template
     - Instruction to keep structure, change scenario
     - Global uniqueness constraints

2. **LLM API Call**
   - Uses OpenAI GPT-4o-mini (or configured model)
   - Requests JSON response format
   - Temperature: 0.7 (balanced creativity)

3. **Response Parsing**
   - Parses JSON response
   - Validates structure:
     - `question_no`: Question identifier
     - `marks`: Total marks
     - `text`: Question stem/scenario
     - `subquestions`: Array of sub-questions with labels and marks

4. **Validation**
   - Checks for empty question text
   - Checks for empty sub-question text
   - Validates JSON structure

5. **Diagram Handling** (if needed)
   - If `needs_diagram = True`:
     - **Primary Method**: DALL·E 3 Image Generation
       - After question approval, generates image using OpenAI DALL·E 3 API
       - Uses question text and sub-question text as prompt
       - Enhances prompt for technical diagrams (ER, Normalization, SQL, etc.)
       - Downloads and saves image to `data/outputs/model_papers/images/`
       - Adds image references to draft: `diagram_image_path`, `diagram_image_url`
     - **Fallback Method 1**: Mermaid Code
       - If DALL·E fails, uses Mermaid code (if available)
       - Renders Mermaid to image using Kroki API
     - **Fallback Method 2**: Text Placeholder
       - If both DALL·E and Mermaid fail, uses text placeholder
       - Format: `[DIAGRAM PLACEHOLDER: Draw the {diagram_type} diagram...]`
   - **Note**: DALL·E images are used for generated exam questions. Mermaid code serves as fallback.

**Output**: Draft question dictionary

**Error Handling**: If API call fails or parsing fails, raises exception for retry

---

#### Step 2.2.4: Quality Review

**Agent**: `QualityCritic` (`backend/app/agents/critic.py`)

**Purpose**: Review draft question for quality, relevance, and correctness

**Process**:

1. **Deterministic Checks** (Immediate, No LLM)
   - **Math Check**: Sub-question marks must sum to total marks
     - If fails: Returns `{"approved": false, "feedback": "MATH ERROR: ..."}`
   - **Structure Check**: Number of sub-questions must match template structure
   - **Hallucination Check**: Rejects if contains:
     - `[figure:`, `slide_`, `fig_`, `page_`, `refer to`, `diagram above`
     - Exception: `[PLACEHOLDER FIGURE]` is allowed
   - **Content Quality Checks**:
     - Text length must be ≥10 characters
     - No vague/subjective questions ("think of", "your opinion")
     - If asks to analyze/normalize, must provide relation schema
     - Mark-to-effort mismatch check
     - Database Systems relevance check
     - Scenario repetition check (same text in multiple sub-questions)
     - Duplicate sub-question check (similarity ≥85%)

2. **LLM-Based Review** (if passes deterministic checks)
   - Sends draft to LLM for:
     - Content relevance verification
     - Hallucination detection
     - Scenario completeness check
   - LLM returns: `{"approved": true/false, "feedback": "..."}`

3. **Fallback**
   - If LLM review fails, auto-approves with warning

**Output**: Review result `{"approved": bool, "feedback": str}`

---

#### Step 2.2.5: Retry Decision

**Location**: `AgentOrchestrator.run_pipeline()` retry loop

**Retry Strategy**:
- **MAX_RETRIES = 3** (4 total attempts: 0, 1, 2, 3)
- **Attempts 0-1**: Generate mode with feedback
- **Attempts 2-3**: Paraphrase mode with feedback
- **Math Error**: Immediate fallback (no retries)

**Decision Logic**:

1. **If Approved**:
   - Normalize labels (a, b, c, ...)
   - **DALL·E Image Generation** (if `needs_diagram = True`):
     - Calls `generate_diagram_for_question()` with question text and diagram type
     - Downloads generated image and saves to `data/outputs/model_papers/images/`
     - Adds `diagram_image_path` and `diagram_image_url` to draft
     - If generation fails, adds `diagram_placeholder` text
   - Add topic label to draft (`main_topic`, `topic_label`)
   - Update global tracking:
     - `used_topics`: Add question topic
     - **`banned_topics`: Add question topic** (prevents reuse in remaining questions)
     - `used_scenarios`: Add scenario snippet
     - `used_question_types`: Add question type
     - `used_modules`: Add syllabus module
     - `used_intents`: Add pattern label
     - `used_template_ids`: Add template ID
   - Save to checkpoint
   - Move to next question

2. **If Rejected**:
   - **Attempt 0-1**: Retry with feedback (generate mode)
   - **Attempt 2-3**: Switch to paraphrase mode, retry
   - **After Max Retries**: Force approval with fallback (see Fallback Mechanisms)

3. **If Math Error**:
   - Skip remaining retries
   - Immediately apply strict template fallback

---

#### Step 2.2.6: Checkpoint Saving

**Location**: `data/outputs/model_papers/generation_checkpoint.json`

**Purpose**: Enable resumable generation if process interrupted

**Process**:
- After each approved question, saves all completed questions
- Includes metadata: `last_update` timestamp
- On restart, loads checkpoint and skips already-completed questions
- **Cleanup**: Checkpoint file is automatically deleted after successful generation completes
- **Retry Handling**: Checkpoint persists through retries and forced approvals (fallback logic)

**Format**:
```json
{
  "questions": [...],
  "last_update": "2024-01-15 14:30:00"
}
```

---

### Step 2.3: Post-Generation Validation

**Location**: `AgentOrchestrator._validate_topic_coverage()`

**Purpose**: Validate overall paper quality

**Checks**:

1. **Topic Dominance Check**
   - No single topic should dominate (>40% of total marks)
   - Logs warning if violation

2. **Topic Diversity Check** (for 4-question papers)
   - **Enforced**: At least 3 distinct topics must be covered across 4 questions
   - This ensures sufficient syllabus coverage
   - Logs warning if insufficient diversity (less than 3 unique topics)

3. **Unique Topics Verification**
   - Verifies that each of the 4 questions has a distinct topic
   - The most frequent topic (forced into Q1) appears exactly once
   - Q2-Q4 topics are verified to be unique from each other and from Q1

**Output**: Validation warnings (non-blocking)

**Note**: Since the final model paper always has exactly 4 questions, the validation rules are tailored for 4-question papers.

---

### Step 2.4: Final Output Generation

**Process**:

1. **JSON Export**
   - Saves to `data/outputs/model_papers/agentic_model_paper.json`
   - Format:
     ```json
     {
       "generated_at": "2024-01-15 14:30:00",
       "mode": "AGENTIC_V1",
       "total_marks": 100,
       "num_questions": 4,
       "topic_distribution": {
         "Q1": {"topic": "ER Modeling", "marks": 25},
         "Q2": {"topic": "Normalization", "marks": 25},
         "Q3": {"topic": "SQL Queries", "marks": 25},
         "Q4": {"topic": "Transactions", "marks": 25}
       },
       "questions": [
         {
           "question_no": "Q1",
           "marks": 25,
           "main_topic": "ER Modeling",
           "topic_label": "ER Modeling",
           "text": "Question stem...",
           "subquestions": [...],
           "needs_diagram": true,
           "diagram_type": "ER",
           "diagram_image_path": "data/outputs/model_papers/images/Q1_1234567890.png",
           "diagram_image_url": "https://oaidalleapiprodscus...",
           "diagram_generated": true,
           "diagram_prompt_used": "Enhanced prompt text..."
         }
       ]
     }
     ```
   - Each question includes:
     - `main_topic` and `topic_label` fields
     - `diagram_image_path` (if DALL·E generated successfully)
     - `diagram_image_url` (temporary OpenAI URL)
     - `diagram_placeholder` (if DALL·E failed)

2. **MongoDB Save**
   - Inserts into MongoDB `papers` collection
   - Enables querying and retrieval of generated papers

3. **PDF Export**
   - Uses `PDFService.generate_pdf()` to create formatted PDF
   - **Diagram Rendering Priority**:
     1. **DALL·E Generated Images**: Embeds DALL·E generated images (if available)
     2. **Mermaid Diagrams**: Renders Mermaid code to images using Kroki API (fallback)
     3. **Text Placeholders**: Uses text placeholders if both methods fail
   - Saves to `data/outputs/model_papers/agentic_model_paper.pdf`

4. **Checkpoint Cleanup**
   - Deletes checkpoint file after successful generation
   - Ensures no stale data remains for next generation

**Output**: Complete model paper in JSON and PDF formats

**Key Features**:
- Exactly 4 questions (Q1-Q4) with unique topics
- Topic distribution summary included in JSON
- Most frequent topic guaranteed in Q1
- Total marks always = 100

---

## Phase 3: Model Paper Generation

The final model paper is a complete exam paper with:

### Structure

1. **Header**
   - Exam title (from blueprint)
   - Total marks: 100
   - Instructions (if configured)

2. **Questions**
   - Each question has:
     - Question number (Q1, Q2, etc.)
     - Total marks
     - Question stem/scenario (text)
     - Sub-questions (a, b, c, etc.) with:
       - Label
       - Marks
       - Text
     - Diagram (if applicable):
       - DALL·E generated image (primary)
       - Mermaid code (fallback)
       - Placeholder text (fallback)

3. **Metadata**
   - Generation timestamp
   - Generation mode
   - Source templates used

### Quality Assurance

- **Mathematical Correctness**: All marks sum correctly
- **Structural Authenticity**: Follows past-paper patterns
- **Syllabus Alignment**: Content matches lecture slides
- **Topic Diversity**: Balanced coverage across modules
- **Uniqueness**: No duplicate scenarios or question types

---

## DALL·E Image Generation Integration

### Overview

The system integrates OpenAI's DALL·E 3 API to generate diagram images for exam questions that require visual elements (e.g., ER diagrams, normalization schemas, transaction schedules).

### Integration Point

**Location**: `backend/app/services/image_generation_service.py`

**Trigger**: After question approval in Step 2.2.5 (Retry Decision), if `needs_diagram = True`

### Process

1. **Image Generation Request**
   - Triggered after question is approved by QualityCritic
   - Extracts diagram-related text from question stem or sub-questions
   - Identifies diagram type (ER, EER, Normalization, SQL, etc.)

2. **Prompt Enhancement**
   - Enhances user prompt for better DALL·E results
   - Adds technical diagram context (e.g., "A clear, professional ER diagram...")
   - Optimizes for academic exam paper style (black and white or minimal colors)

3. **DALL·E API Call**
   - Calls OpenAI DALL·E 3 API with enhanced prompt
   - Parameters:
     - Model: `dall-e-3`
     - Size: `1024x1024` (default)
     - Quality: `standard` (default)
     - Response format: `url` (temporary URL from OpenAI)

4. **Image Download & Storage**
   - Downloads image from temporary OpenAI URL
   - Saves to `data/outputs/model_papers/images/{question_no}_{timestamp}.png`
   - Creates directory if it doesn't exist

5. **Result Handling**
   - **Success**: Adds to draft:
     - `diagram_image_path`: Local file path
     - `diagram_image_url`: Temporary OpenAI URL
     - `diagram_generated`: `true`
     - `diagram_prompt_used`: Enhanced prompt text
   - **Failure**: Adds fallback:
     - `diagram_placeholder`: Text placeholder
     - `diagram_generated`: `false`

### Error Handling

- **API Errors**: Wrapped in try-except with retry logic (exponential backoff)
- **Rate Limits**: Automatic retry with backoff (up to 3 attempts)
- **Network Errors**: Falls back to text placeholder
- **Invalid Responses**: Falls back to text placeholder

### Fallback Chain

1. **DALL·E Generated Image** (Primary)
2. **Mermaid Code Rendering** (Fallback 1 - if DALL·E fails)
3. **Text Placeholder** (Fallback 2 - if both fail)

### PDF Integration

The PDF service (`PDFService.generate_pdf()`) renders diagrams in this priority:
1. DALL·E generated images (from `diagram_image_path`)
2. Mermaid-rendered images (from `mermaid_code`)
3. Text placeholders (from `diagram_placeholder`)

### Example Output

```json
{
  "question_no": "Q1",
  "marks": 25,
  "needs_diagram": true,
  "diagram_type": "ER",
  "diagram_image_path": "data/outputs/model_papers/images/Q1_1705123456.png",
  "diagram_image_url": "https://oaidalleapiprodscus.blob.core.windows.net/...",
  "diagram_generated": true,
  "diagram_prompt_used": "A clear, professional Entity-Relationship (ER) diagram showing database entities, attributes, and relationships. Draw an ER diagram for a university database system..."
}
```

### Configuration

- **API Key**: Uses `OPENAI_API_KEY` from environment variables (same as LLM)
- **Model**: DALL·E 3 (default)
- **Image Size**: 1024x1024 (default, can be 1792x1024 or 1024x1792)
- **Quality**: standard (default, can be "hd" for higher quality)

### Cost Considerations

- DALL·E 3 pricing: ~$0.04 per image (1024x1024, standard quality)
- Images are generated only for questions that require diagrams
- Failed generations don't incur costs (no charge for failed API calls)

---

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│ PREPROCESSING DATA FLOW                                          │
└─────────────────────────────────────────────────────────────────┘

Past Papers PDFs
    │
    ├─→ [OCR/Text Extraction] ─→ Blueprint JSONs
    │                                    │
    ├─→ [Diagram Extraction] ───────────┼─→ Diagrams Manifest
    │                                    │
    └─→ [Text Chunking] ────────────────┴─→ Chunks JSONL
                                                │
                                                ▼
                                        Structure Analysis
                                                │
                                                ├─→ Exam Blueprint
                                                ├─→ Topic Clusters
                                                └─→ Template Questions
                                                        │
                                                        ▼
                                                Canonical Templates
                                                        │
                                                        ▼
                                                MongoDB Sync

Lecture Slides PDFs
    │
    ├─→ [Text Extraction] ─→ Slide Chunks
    │
    ├─→ [Figure Extraction] ─→ Figure Metadata
    │
    └─→ [Embedding] ─→ FAISS Index
            │
            └─→ Ready for RAG

┌─────────────────────────────────────────────────────────────────┐
│ AGENTIC PIPELINE DATA FLOW                                      │
└─────────────────────────────────────────────────────────────────┘

Blueprint
    │
    ├─→ [Analyst] ─→ Validated Blueprint
    │
    └─→ For Each Slot:
            │
            ├─→ [Template Selection] ─→ Template
            │
            ├─→ [Researcher] ─→ Context (from FAISS)
            │
            ├─→ [Writer] ─→ Draft Question
            │
            ├─→ [Critic] ─→ Review Result
            │
            └─→ [Retry Loop] ─→ Approved Question
                    │
                    └─→ Checkpoint Save

All Questions
    │
    ├─→ [Validation] ─→ Topic Coverage Check
    │
    ├─→ [JSON Export] ─→ agentic_model_paper.json
    │
    ├─→ [MongoDB Save] ─→ papers collection
    │
    └─→ [PDF Export] ─→ agentic_model_paper.pdf
```

---

## Key Components Deep Dive

### 1. SyllabusClassifier

**Location**: `backend/app/agents/orchestrator.py`

**Purpose**: Classify templates into syllabus modules for balanced selection

**Technology**: SentenceTransformer (`all-MiniLM-L6-v2`)

**Modules**:
- Introduction & ER Modeling
- Relational Model & Normalization
- SQL & Queries
- Transactions & Concurrency
- Indexing & Storage
- Advanced & Other

**Usage**: Pre-computes embeddings for module keywords, then classifies template text using cosine similarity.

---

### 2. Diagram Service

**Location**: `backend/app/services/diagram_service.py`

**Purpose**: Handle diagram reconstruction and injection

**Features**:
- Reconstructs diagrams from past papers
- Converts to Mermaid format
- Caches reconstructed diagrams for reuse
- Injects diagrams into generated questions when needed

---

### 3. PDF Service

**Location**: `backend/app/services/pdf_service.py`

**Purpose**: Generate formatted PDF from JSON paper

**Features**:
- Formats questions with proper numbering
- Handles sub-questions (a, b, c, etc.)
- Renders Mermaid diagrams (if applicable)
- Creates professional exam paper layout

---

### 4. MongoDB Integration

**Collections**:
- `canonical_templates`: Pre-analyzed question patterns per position
- `templates`: Raw question templates from past papers
- `papers`: Generated model papers

**Usage**: Enables fast template retrieval and paper storage/retrieval.

---

## Error Handling & Fallbacks

### Fallback Hierarchy

1. **Template Selection Fallbacks**
   - Canonical → MongoDB templates → Random → Generic

2. **Writer Mode Fallback**
   - Generate mode → Paraphrase mode

3. **Math Error Fallback**
   - Immediate template fallback (no retries)

4. **Quality Error Fallback**
   - Sanitization → Strict template fallback → Minimal valid draft

5. **Blueprint Fallback**
   - Default blueprint (4 questions, 25 marks each)

6. **LLM API Fallback**
   - Retry → Auto-approve (critic)

7. **Resource Loading Fallback**
   - Disable feature, use alternative

### Retry Logic

- **MAX_RETRIES = 3** (4 total attempts)
- **Generate Mode**: Attempts 0-1
- **Paraphrase Mode**: Attempts 2-3
- **Math Errors**: No retries (immediate fallback)
- **API Failures**: Retry with exponential backoff

### Checkpoint System

- Saves progress after each approved question
- Enables resumable generation
- Automatically cleans up after successful completion

---

## Summary

The model paper generation process follows this sequence:

1. **Preprocessing** (One-time):
   - Extract past papers → Blueprints
   - Extract lecture slides → Embeddings + FAISS index
   - Analyze structure → Exam blueprint + Templates
   - Generate canonical templates → MongoDB

2. **Agentic Pipeline** (On-demand):
   - Load blueprint
   - For each question slot:
     - Select template
     - Research context
     - Write question
     - Review quality
     - Retry if needed
   - Validate coverage
   - Export JSON + PDF

3. **Output**:
   - Complete model paper (JSON + PDF)
   - Stored in MongoDB
   - Ready for use

The system ensures:
- **Authenticity**: Follows past-paper patterns
- **Quality**: Multiple validation layers
- **Syllabus Alignment**: Uses lecture slide content
- **Diversity**: Balanced topic coverage (at least 3 distinct topics across 4 questions)
- **Reliability**: Comprehensive fallback mechanisms
- **Structure**: Always generates exactly 4 questions (Q1-Q4) with 100 total marks
- **Topic Uniqueness**: Each question has a distinct topic, with most frequent topic forced into Q1

---

## File Locations Reference

### Preprocessing Scripts
- `backend/scripts/pastpaper_extract.py` - Past paper extraction
- `backend/scripts/lectureslide_extract.py` - Lecture slide extraction
- `backend/scripts/structure_topics_template.py` - Structure analysis
- `backend/scripts/template_analyzer.py` - Canonical template generation

### Agentic Pipeline
- `backend/app/agents/orchestrator.py` - Main orchestrator
- `backend/app/agents/analyst.py` - Blueprint analyst
- `backend/app/agents/researcher.py` - Content researcher
- `backend/app/agents/writer.py` - Question writer
- `backend/app/agents/critic.py` - Quality critic

### Entry Points
- `run_agentic.py` - Standalone agentic generation
- `run_all.py` - Full preprocessing + agentic pipeline
- `start_server.py` - API server

### Output Directories
- `data/text_extraction_hybrid/` - Past paper extractions
- `data/lecture_slides_extraction/` - Lecture slide extractions
- `data/slides_embeddings/` - Embeddings and FAISS index
- `data/artifacts/` - Blueprints, templates, canonical templates
- `data/outputs/model_papers/` - Generated model papers

---

## Summary: Key Enforcement Rules

### 4-Question Generation (Hard Enforced)
- **Blueprint Generation**: Always creates exactly 4 slots (Q1-Q4)
- **Blueprint Validation**: Limits to first 4 slots if more exist
- **Orchestrator**: Processes only first 4 slots, ignores any additional slots
- **Output**: Final paper always contains exactly 4 questions

### Topic Frequency Analysis
- **Scope**: Analyzes ALL question positions (Q1, Q2, Q3, Q4, Q5, Q6, etc.) from latest 6 papers
- **Purpose**: Calculate overall topic frequency across all positions
- **Result**: Most frequent topic is identified and forced into Q1
- **Note**: Q5+ positions inform frequency but are NOT included in final blueprint

### Unique Topics Enforcement
- **Q1**: Most frequent topic (forced, cannot be changed)
- **Q2-Q4**: Unique topics (filtered to avoid duplicates)
- **Banned Topics**: Each used topic is added to `banned_topics` set
- **Writer Constraints**: Banned topics are explicitly passed to prevent repetition

### Total Marks Enforcement
- **Canonical Total**: Always 100 marks
- **Distribution**: Marks distributed across 4 slots (typically 25 marks each, but can vary)
- **Validation**: Total marks reconciliation ensures sum = 100

### Topic Diversity Validation
- **Minimum**: At least 3 distinct topics across 4 questions
- **Maximum**: No single topic should exceed 40% of total marks
- **Verification**: Post-generation validation checks topic uniqueness

### Diagram Handling
- **Lecture Slides**: Vision AI extracts captions only (no Mermaid code)
- **Generated Questions**: Mermaid code used for ER/EER diagrams in exam questions
- **Rendering**: Kroki API renders Mermaid to images for PDF export
- **Fallback**: Text placeholders if diagram generation/rendering fails

---

**End of Documentation**
