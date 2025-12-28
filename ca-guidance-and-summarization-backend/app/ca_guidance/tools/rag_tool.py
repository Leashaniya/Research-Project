"""RAG tool for CrewAI agents to query lecture materials."""

import os
import logging
from typing import Optional
from crewai.tools import tool
from app.core.config import settings
from app.ca_guidance.tools.tts_tool import text_to_speech_wav

# Set tokenizers parallelism to avoid warnings
os.environ["TOKENIZERS_PARALLELISM"] = "false"
# Set PyTorch to use single thread to avoid multiprocessing issues on macOS
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"

# Try to load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from app.ca_guidance.rag.ingestion.vectorstore_builder import load_vectorstore
from app.ca_guidance.rag.chains.rag_chain import create_rag_chain
from app.ca_guidance.rag.config.settings import VECTORSTORE_DIR

logger = logging.getLogger(__name__)

# Global cache for RAG chain
_rag_chain_cache: Optional[object] = None


def _get_rag_chain():
    """Get or create the RAG chain (cached)."""
    global _rag_chain_cache
    
    if _rag_chain_cache is None:
        try:
            logger.info("Initializing RAG chain...")
            vectorstore = load_vectorstore(VECTORSTORE_DIR)
            
            if vectorstore is None:
                logger.warning("No vectorstore found. RAG tool will not work until vectorstore is built.")
                return None
            
            _rag_chain_cache = create_rag_chain(
                vectorstore, 
                model_name=settings.RAG_SUMMARY_MODEL,
                provider=settings.RAG_SUMMARY_PROVIDER,
                base_url=settings.OLLAMA_BASE_URL,
                )

            logger.info("RAG chain initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize RAG chain: {e}", exc_info=True)
            return None
    
    return _rag_chain_cache


@tool("Query Lecture Materials")
def query_lecture_materials(query: str) -> str:
    """
    Query lecture materials and course documents using RAG (Retrieval-Augmented Generation).
    This tool searches through uploaded lecture PDFs, extracts relevant information including text, tables, and diagrams,
    and provides answers based on the course content.
    
    Use this tool when you need to:
    - Find information about programming concepts, design patterns, or course topics
    - Get examples from lecture materials
    - Understand concepts explained in the course documents
    - Reference diagrams or tables from lectures
    
    Args:
        query: The question or query to search for in the lecture materials.
               Be specific about what you're looking for (e.g., "What is the singleton pattern?",
               "Explain the factory method pattern with examples", "Show me UML diagrams for design patterns").
    
    Returns:
        A detailed answer based on the lecture materials, including relevant context and examples.
        If images are found, they will be referenced in the answer with special markers: [IMAGE:filename.jpg]
        If no vectorstore is available, returns an error message.
    """
    try:
        rag_chain = _get_rag_chain()
        
        if rag_chain is None:
            return "RAG system is not available. The vectorstore needs to be built first by ingesting lecture PDFs."
        
        result = rag_chain.invoke({"question": query})
        answer = result.get("answer", str(result)) if isinstance(result, dict) else str(result)
        images = result.get("images", []) if isinstance(result, dict) else []
        
        # Add image references to the answer
        if images:
            from pathlib import Path
            image_refs = []
            for img_path in images:
                img_name = Path(img_path).name if not isinstance(img_path, str) or '/' in img_path else img_path
                image_refs.append(f"[IMAGE:{img_name}]")
            
            if image_refs:
                answer += "\n\n**Related Images:**\n" + "\n".join(image_refs)
        
        return answer
    except Exception as e:
        logger.error(f"Error querying lecture materials: {e}", exc_info=True)
        return f"An error occurred while querying lecture materials: {str(e)}"


@tool("Summarize Lecture Materials")
def summarize_lecture_materials(topic: str) -> str:
    """
    Create a comprehensive summary of lecture materials on a specific topic using RAG.
    This tool searches through uploaded lecture PDFs and generates a well-structured summary
    with relevant images and diagrams.
    
    Use this tool when you need to:
    - Create summaries of specific topics or concepts from the course
    - Get an overview of lecture content on a particular subject
    - Generate study guides or review materials
    
    Args:
        topic: The topic or subject to summarize (e.g., "Entity-Relationship Diagrams",
               "Normalization", "SQL Queries", "Transaction Management").
    
    Returns:
        A comprehensive summary based on the lecture materials, including relevant context and examples.
        If images are found, they will be referenced in the summary with special markers: [IMAGE:filename.jpg]
        If no vectorstore is available, returns an error message.
    """
    try:
        rag_chain = _get_rag_chain()
        
        if rag_chain is None:
            return "RAG system is not available. The vectorstore needs to be built first by ingesting lecture PDFs."
        
        # Create a summary-focused query
        summary_query = f"Provide a comprehensive summary of {topic}. Include key concepts, main ideas, important details, and examples. If there are diagrams or visual aids related to this topic, make sure to reference them."
        
        result = rag_chain.invoke({"question": summary_query})
        answer = result.get("answer", str(result)) if isinstance(result, dict) else str(result)
        images = result.get("images", []) if isinstance(result, dict) else []
        
        # Add image references to the summary
        if images:
            from pathlib import Path
            image_refs = []
            for img_path in images:
                img_name = Path(img_path).name if not isinstance(img_path, str) or '/' in img_path else img_path
                image_refs.append(f"[IMAGE:{img_name}]")
            
            if image_refs:
                answer += "\n\n**Related Images:**\n" + "\n".join(image_refs)

        # Generate audio for the summary
        try:
            audio_path = text_to_speech_wav(answer)
            audio_url = "/audio/" + audio_path.split("/")[-1]
            answer += f"\n\n**Audio:** {audio_url}"
        except Exception as tts_err:
            logger.error(f"TTS generation failed: {tts_err}", exc_info=True)

        return answer
    except Exception as e:
        logger.error(f"Error summarizing lecture materials: {e}", exc_info=True)
        return f"An error occurred while summarizing lecture materials: {str(e)}"

