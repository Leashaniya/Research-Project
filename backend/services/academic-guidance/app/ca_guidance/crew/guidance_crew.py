import logging
import re
from crewai import Crew, Task
from app.core.config import settings
from app.ca_guidance.agents.guidance_agent import guidance_agent
from app.ca_guidance.agents.event_scheduler_agent import event_scheduler_agent

logger = logging.getLogger(__name__)


def _chunk_assignment_text(text: str, max_chars: int = 24000, overlap: int = 1000) -> list[str]:
    """
    Split a long assignment into chunks so the guidance agent can process the full document.
    Uses paragraph boundaries and a small overlap so nothing is lost at chunk edges.
    """
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        # Try to break at a nearby paragraph boundary
        boundary = text.rfind("\n\n", start + 1200, end)
        if boundary == -1 or boundary <= start + 1200:
            boundary = end
        if boundary <= start:
            boundary = min(start + max_chars, len(text))
        chunk = text[start:boundary].strip()
        if chunk:
            chunks.append(chunk)
        if boundary >= len(text):
            break
        next_start = max(0, boundary - overlap)
        if next_start <= start:
            next_start = boundary
        start = next_start
    return [c for c in chunks if c]


def _extract_question_markers(text: str, limit: int = 45) -> list[str]:
    """
    Extract question headings/markers so guidance can explicitly cover full document.
    """
    if not text:
        return []
    markers: list[str] = []
    seen = set()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    patterns = [
        r'^(Q(?:uestion)?\s*\d+[\]:.)-]?\s*.*)$',
        r'^(\d+[\).]\s+.+)$',
        r'^([A-Za-z][\).]\s+.+)$',
        r'^(\([a-z]\)\s+.+)$',  # (a) sub-items
        r'^(Task\s*\d+[:.)-]?\s*.*)$',
        r'^(Part\s*\d+[:.)-]?\s*.*)$',
        r'^((?:Section|Chapter)\s*\d+[:\s.).-]?\s*.+)$',
    ]
    for ln in lines:
        for p in patterns:
            m = re.match(p, ln, flags=re.IGNORECASE)
            if m:
                marker = m.group(1).strip()
                key = marker.lower()
                if key not in seen:
                    seen.add(key)
                    markers.append(marker[:220])
                break
        if len(markers) >= limit:
            break
    return markers


def create_guidance_crew(assignment_text: str, access_token: str):
    """
    Create a CrewAI crew to handle DBMS assignment guidance.
    
    Args:
        assignment_text: The text extracted from the assignment PDF
        access_token: OAuth access token for calendar operations
    
    Returns:
        Crew instance ready to execute
    """
    # Set access token for calendar tool
    from app.ca_guidance.tools.calendar_tool import set_access_token
    set_access_token(access_token)
    
    # Task 1: Analyze assignment and produce DBMS guidance
    # If the assignment is long, split it into chunks so every part is read.
    chunks = _chunk_assignment_text(assignment_text)
    question_markers = _extract_question_markers(assignment_text)
    question_list_text = "\n".join(f"- {q}" for q in question_markers) if question_markers else "- (No explicit numbered markers detected; still cover all assignment sections.)"
    guidance_tasks: list[Task] = []

    for idx, chunk in enumerate(chunks, start=1):
        guidance_tasks.append(
            Task(
                description=f"""
                You are processing PART {idx} of {len(chunks)} of a Database Management Systems (DBMS) assignment.

                You MUST treat this part as an integral section of the full assignment and:
                - Carefully read this ENTIRE part from start to finish (every line, table row, and bullet).
                - For every question, sub-question, or numbered/lettered item in THIS PART, provide corresponding guidance or a solution.
                - Do not skip any question in this part, even if it looks similar to previous ones.
                - If this chunk overlaps another part, do not repeat long boilerplate—still answer everything that appears in the text above.
                - The combined parts must cover the **whole** assignment document; never assume another part will answer a question that appears here.

                Assignment Text (Part {idx} of {len(chunks)}):
                {chunk}

                Known question/section markers detected from the full assignment (full document—not every marker may appear in this chunk):
                {question_list_text}

                **Per-question structure (mandatory for this part):**
                - Go through the assignment text **in order** and, for **every** question, sub-question, or clearly separated task you find in THIS chunk, output a block with:
                  1) A markdown heading `###` that labels that item (reuse the assignment's numbering/lettering, e.g. `### Question 2`, `### (b)`, `### Part III`).
                  2) The **full written answer** for that item first (all sub-parts, SQL, steps, or theory—nothing withheld for later).
                  3) **Only after** that written answer: if that **same** item asks for a diagram/schema/flowchart, call **generate_assignment_diagram** and paste the returned `[IMAGE:filename.png]` on the **next lines**, still inside the same `###` section—never move diagrams for Question 2 to the end of the document.
                - Keep names, numbers, and constraints **exactly as stated** in the assignment (course codes, entity names, cardinalities, deadlines in text). Do not substitute unrelated toy examples unless the assignment is generic.

                Your output for this part MUST:
                - Be written in clear, structured markdown format.
                - Produce **DBMS-specific guidance**, not programming guidance.
                - Write all notes and explanations as **normal prose text** (plain paragraphs and lists). Do not put explanatory notes inside code blocks; reserve code blocks only for actual SQL, code, or diagram syntax.
                - Provide step-by-step instructions, explanations, or solutions based on the assignment type.
                - If the CA asks for an **ER / EER / conceptual or relational schema** (e.g. draw, create, diagram, schema, model entities):
                    → Call **generate_assignment_diagram** with `diagram_type` **er_diagram** and a `description` covering every entity, attribute (PK, multivalued, composite, relationship-descriptive), relationship type (binary, ternary, ISA, aggregation), and cardinalities **for that question only**.
                    → The tool returns `[IMAGE:filename.png]` (Chen-style Graphviz): paste that line **after** the answer paragraphs for that question, outside code fences.
                    → Style: entity rectangles, relationship diamonds, attribute ovals (no attributes inside entity boxes), triangle for ISA, double rectangle for weak entities; no Crow's Foot.
                    → Add one short sentence **immediately after** each `[IMAGE:...]` line describing what the diagram shows.
                    → If several questions each need an ER diagram, call the tool **once per question** with a description scoped to that question so each `[IMAGE:...]` stays under the correct `###` heading.
                - If the assignment asks for a **flowchart** or other non-ER diagram and a PNG is appropriate:
                    → Call **generate_assignment_diagram** with `diagram_type` **flowchart** or **general** and a concise process description **for that question only**.
                    → If the tool returns `[IMAGE:filename.png]`, paste that line **after** that question's written answer, outside fenced code blocks.
                - If no diagram is requested, you may use optional Mermaid or ASCII in a fenced code block only.
                - **Never** output ```dot or ```graphviz for ER/EER/schema diagrams—the server will not render that as an image. For ER you **must** use **generate_assignment_diagram** and paste only the returned `[IMAGE:...]` line(s).
                - If SQL queries are required: provide full working SQL statements in a code block.
                - If conceptual answers are required: provide accurate, lecture-aligned explanations as normal text.
                - If the assignment involves design (ER models, EER models, normalization, schema design, constraints):
                    → Break down each step clearly in normal text.
                    → Explain reasoning and methodology.
                - If this part contains multiple questions:
                    → Provide solutions for each question or guidance for each part.
                - You MUST explicitly label every covered question/section **that appears in the chunk above** (use headings like `### Question ...` or `### Part ...`) so coverage is auditable.
                - Markers listed may belong to other parts of the assignment: do **not** write stub lines such as "Not found in this part", "N/A for this part", or "See other part" for those—**omit** them from this part's output entirely.
                - For non-ER diagrams only, you may use Mermaid in a fenced block. For ER/schema, **only** `[IMAGE:...]` from the diagram tool (no raw Graphviz DOT in the answer).

                IMPORTANT:
                - Use the **query_lecture_materials** tool to verify accuracy based on course content.
                - Align all explanations with the uploaded DBMS lectures: ER model, EER, weak entities, ISA, normalization, traps, etc.
                - Do NOT include programming setup steps (Python installation, code files, etc.).
                - Tailor your answer to the nature of the assignment (ERD, SQL, theory, design) for this part.

                You are NOT required to follow any fixed structure such as:
                - Project Overview
                - Setup & Installation
                - Complete Program Code
                - Testing Instructions
                
                Instead, produce a **DBMS-specific solution guide** appropriate for the content in THIS PART.

                After completing the DBMS solution for this part, add the following sections:

                ### Related Web Resources
                - You MUST call the `duckduckgo_search` tool with a short topic related to the assignment 
                (for example: "ER modeling DBMS", "normalization DBMS", "SQL queries DBMS", etc.).
                - The tool will return:
                    - Valid article links  
                    - Valid YouTube video links  
                - Simply insert the tool output **as-is** below this heading.
                - Do NOT rewrite or summarize the tool output; do NOT restate the links manually.
                - Every URL MUST be a clickable markdown link: use exactly `[Title of resource](URL)` or `[URL](URL)` so links render as links. Never output bare URLs as plain text.
                - These links are only for reference; do NOT use their content in the main explanation.
                - Output ONLY the raw markdown document. Do NOT wrap your entire response in a code block (no ```markdown or ``` at the start/end). Your reply must be the guidance itself so it renders as formatted text.
                """,
                agent=guidance_agent,
                expected_output=(
                    f"DBMS guidance for assignment part {idx} of {len(chunks)} "
                    "with step-by-step explanations aligned with lecture materials (raw markdown, not wrapped in a code block)."
                ),
            )
        )

    # Task 2: Find deadline and schedule calendar event
    scheduling_task = Task(
        description=f"""
        You are given the full assignment text below:

        --- ASSIGNMENT TEXT START ---
        {assignment_text}
        --- ASSIGNMENT TEXT END ---
        
        You MUST carefully scan the assignment text and extract ANY date-like or deadline-like phrase.

        A deadline may appear in MANY forms, including:
        - "Deadline is 31st of December 2025 11:59 PM"
        - "Submit on or before 1st December 2025"
        - "Due: 2025-12-01"
        - "Final submission before 11:59 PM on 01/12/2025"
        - Or ANY phrase containing a date/time.

        IMPORTANT RULES:
        1. DO NOT ignore dates inside long sentences.
        2. DO NOT try to convert or clean the date. Extract the RAW PHRASE.
        3. DO NOT assume YYYY-MM-DD is required. Any natural-language date is valid.
        4. If there is ANY POSSIBLE deadline, you MUST extract it.
        5. ONLY IF no date-like pattern exists anywhere in the text, say no deadline was found.

        If a deadline is found:
        - Call the create_calendar_event tool with:
            title: "Submit: [Assignment Title]"
            start_date: EXACT raw deadline phrase you extracted
            duration_hours: 1

        If no deadline is found:
        - Do NOT call the tool.
        -Simply state that no deadline was found.

        Return:
        - The extracted deadline phrase or "None"
        - Whether the event was created
        - Any message returned by the tool
        """,
        agent=event_scheduler_agent,
        expected_output="A message confirming whether a deadline was found and whether the event was created.",
    )

    # Task 3: Insert calendar confirmation into final guide
    finalize_task = Task(
        description=f"""
        Combine:
        - All DBMS guidance documents from the guidance tasks (there may be multiple parts)
        - The calendar scheduling result

        Your job is to produce ONE final combined document.

        IMPORTANT:
        - You MUST include the entire DBMS guidance content from **every** guidance task in your response.
        - Do NOT say things like "the solution is provided above".
        - Do NOT summarize or shorten the guidance unless explicitly asked.
        - Preserve all steps, explanations, and answers from each part so that the final document covers the entire assignment.
        - Preserve every `[IMAGE:filename]` line from the guidance tasks exactly (do not remove or rewrite filenames); these are generated PNG diagram images.
        - Keep each `[IMAGE:...]` in the **same** `### Question / Part / ...` section as the prose that answers that item—**below** that answer, never orphaned at the end of the document unless that item is the last question.
        - Remove any ```dot / ```graphviz ER drafts from part outputs; ER diagrams must appear only as `[IMAGE:...]` lines from the tool, not raw DOT in the final document.
        - Preserve fenced **Mermaid** or **SQL** blocks from parts when they are not ER Graphviz.
        - Start by reproducing the full combined guidance (you may organize it by question number or by assignment section).
        - Use the detected markers below only to **organize** headings where a question was actually answered in the parts. Do **not** add empty stub sections.
        - Never use placeholder phrases such as "Not found in this part", "Not in this part", "N/A for this part", or similar—if something was not addressed anywhere, **omit** it rather than stating a placeholder.
        - Detected question/section markers (reference only):
        {question_list_text}
        - Do NOT output only diagrams. Keep full prose guidance and keep each relevant diagram **after** its question's answer in that section.
        - After each pasted `[IMAGE:...]` line, add **one short plain sentence** describing what the diagram shows (entities/relationships or process), so students can follow without opening the file alone.
        - Then at the very end, add a section:

        Add a final short section at the end titled:
        ### Deadline / Calendar Confirmation

        If a deadline was found: mention the event creation.
        If no deadline was found: state that no deadline was detected.

        Return the final completed guidance.
        """,
        agent=guidance_agent,
        expected_output="A complete DBMS guidance document with a final deadline confirmation section.",
        context=[*guidance_tasks, scheduling_task],
    )

    # Create crew
    crew = Crew(
        agents=[guidance_agent, event_scheduler_agent],
        tasks=[*guidance_tasks, scheduling_task, finalize_task],
        verbose=True,
    )

    return crew