import logging
from crewai import Crew, Task
from app.core.config import settings
from app.ca_guidance.agents.guidance_agent import guidance_agent
from app.ca_guidance.agents.event_scheduler_agent import event_scheduler_agent

logger = logging.getLogger(__name__)


def _chunk_assignment_text(text: str, max_chars: int = 8000) -> list[str]:
    """
    Split a long assignment into smaller chunks so the guidance
    agent can reliably read and process the entire document.
    """
    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        # Try to break at a nearby paragraph boundary
        boundary = text.rfind("\n\n", start, end)
        if boundary == -1 or boundary <= start + 1000:
            boundary = end
        chunks.append(text[start:boundary].strip())
        start = boundary
    return [c for c in chunks if c]


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
    guidance_tasks: list[Task] = []

    for idx, chunk in enumerate(chunks, start=1):
        guidance_tasks.append(
            Task(
                description=f"""
                You are processing PART {idx} of {len(chunks)} of a Database Management Systems (DBMS) assignment.

                You MUST treat this part as an integral section of the full assignment and:
                - Carefully read this ENTIRE part from start to finish.
                - For every question, sub-question, or numbered/lettered item in THIS PART, provide corresponding guidance or a solution.
                - Do not skip any question in this part, even if it looks similar to previous ones.

                Assignment Text (Part {idx} of {len(chunks)}):
                {chunk}

                Your output for this part MUST:
                - Be written in clear, structured markdown format.
                - Produce **DBMS-specific guidance**, not programming guidance.
                - Write all notes and explanations as **normal prose text** (plain paragraphs and lists). Do not put explanatory notes inside code blocks; reserve code blocks only for actual SQL, code, or diagram syntax.
                - Provide step-by-step instructions, explanations, or solutions based on the assignment type.
                - If the assignment requires drawing: describe how to draw the ERD/EERD; put any diagram syntax (e.g. ASCII, Mermaid, or diagram code) inside a markdown fenced code block so it is clearly a diagram.
                - If SQL queries are required: provide full working SQL statements in a code block.
                - If conceptual answers are required: provide accurate, lecture-aligned explanations as normal text.
                - If the assignment involves design (ER models, EER models, normalization, schema design, constraints):
                    → Break down each step clearly in normal text.
                    → Explain reasoning and methodology.
                - If this part contains multiple questions:
                    → Provide solutions for each question or guidance for each part.
                - If diagrams are needed: put them in markdown (e.g. a fenced code block for diagram text/ASCII, or use ![alt](url) for images). Do not mix diagram content with notes in one block.

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
        description="""
        Combine:
        - All DBMS guidance documents from the guidance tasks (there may be multiple parts)
        - The calendar scheduling result

        Your job is to produce ONE final combined document.

        IMPORTANT:
        - You MUST include the entire DBMS guidance content from **every** guidance task in your response.
        - Do NOT say things like "the solution is provided above".
        - Do NOT summarize or shorten the guidance unless explicitly asked.
        - Preserve all steps, explanations, and answers from each part so that the final document covers the entire assignment.
        - Start by reproducing the full combined guidance (you may organize it by question number or by assignment section).
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