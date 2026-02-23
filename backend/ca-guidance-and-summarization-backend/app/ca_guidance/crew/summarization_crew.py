import logging
from crewai import Crew, Task
from app.ca_guidance.agents.summarization_agent import summarization_agent

logger = logging.getLogger(__name__)

def create_summarization_crew(topic: str):
    """
    Create a CrewAI crew to handle lecture material summarization.
    
    Args:
        topic: The topic or subject to summarize
    
    Returns:
        Crew instance ready to execute
    """
    # Task: Create comprehensive summary
    summarization_task = Task(
        description=f"""
        Create a comprehensive, well-structured summary of the following topic from the lecture materials:
        
        Topic: {topic}
        
        Your summary MUST include:
        
        ### Overview
        A brief introduction to the topic and its importance.
        
        ### Key Concepts
        List and explain the main concepts related to this topic.
        Use the summarize_lecture_materials tool to retrieve relevant information from the course materials.
        
        ### Main Points
        Break down the topic into clear, organized main points with explanations.
        
        ### Examples and Applications
        Include relevant examples, use cases, or applications from the lecture materials.
        
        ### Visual Aids
        If diagrams, tables, or images are available for this topic, reference them appropriately.
        The tool will automatically include image references in the format [IMAGE:filename.png].
        
        ### Summary
        Provide a concise summary of the key takeaways.
        
        IMPORTANT:
        - Use the summarize_lecture_materials tool to retrieve information from the course materials
        - Ensure the summary is accurate and aligned with the course content
        - Write notes and explanations as normal prose text; put diagrams in markdown (e.g. fenced code block for diagram syntax, or ![alt](url) for images)
        - Format any URLs as markdown links [text](URL) so they render as clickable links
        - Include references to diagrams and images when available
        - Make the summary clear, well-organized, and easy to understand
        - Focus on the most important information from the lecture materials
        """,
        agent=summarization_agent,
        expected_output="A comprehensive markdown summary with all required sections including relevant images."
    )
    
    # Create crew with task
    crew = Crew(
        agents=[summarization_agent],
        tasks=[summarization_task],
        verbose=True,
    )
    
    return crew

