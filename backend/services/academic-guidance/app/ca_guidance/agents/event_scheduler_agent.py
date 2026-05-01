import os
from crewai import Agent
from app.core.config import settings
from app.ca_guidance.tools.calendar_tool import create_calendar_event

# Set environment variable for CrewAI to use OpenAI
os.environ["OPENAI_API_KEY"] = settings.OPENAI_API_KEY

event_scheduler_agent = Agent(
    role="Calendar Scheduling Assistant",
    goal="Extract deadlines and schedule them in Google Calendar.",
    backstory=(
        "You ALWAYS extract deadlines from assignment text. "
        "A deadline can appear in natural language (e.g., '31st of December 2025 11:59 PM'). "
        "You can pass the FULL RAW DEADLINE PHRASE to the create_calendar_event tool. "
        "Do NOT restrict yourself to numeric or cleaned dates. "
        "If ANY date-like phrase exists in a submission/due context, you MUST call create_calendar_event—"
        "never stop after only describing the date in prose."
    ),
    tools=[create_calendar_event],
    verbose=True,
    allow_delegation=False,
    llm="gpt-4o",
)
