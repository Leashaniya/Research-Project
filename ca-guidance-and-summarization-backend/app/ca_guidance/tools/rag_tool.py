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
def summarize_lecture_materials(topic: str):
    """
    Create a comprehensive summary of lecture materials on a specific topic using RAG.
    This tool searches through uploaded lecture PDFs and generates a well-structured summary
    with relevant images, diagrams, and audio_url.
    
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
            return {
                "topic": topic,
                "summary": "RAG system is not available. The vectorstore needs to be built first by ingesting lecture PDFs.",
                "images": [],
                "audio_url": None
            }
        
        # Create a summary-focused query
        summary_query = (f"Provide a comprehensive summary of {topic}. Include key concepts, main ideas, important details, and examples. If there are diagrams or visual aids related to this topic, make sure to reference them.")
        
        result = rag_chain.invoke({"question": summary_query})
        answer = result.get("answer", str(result)) if isinstance(result, dict) else str(result)
        images = result.get("images", []) if isinstance(result, dict) else []
        
        # Add image references to the summary
        if images:
            from pathlib import Path
            image_refs = []
            for img_path in images:
                img_name = Path(img_path).name if isinstance(img_path, str) else Path(img_path).name
                image_refs.append(f"[IMAGE:{img_name}]")
            
            if image_refs:
                answer += "\n\n**Related Images:**\n" + "\n".join(image_refs)

        # Generate audio for the summary
        try:
            audio_path = text_to_speech_wav(answer)
            audio_url = f"/audio/{Path(audio_path).name}"
        except Exception as tts_err:
            logger.error(f"TTS generation failed: {tts_err}", exc_info=True)

        return {
            "topic": topic,
            "summary": answer,
            "images": images,
            "audio_url": audio_url
        }
    except Exception as e:
        logger.error(f"Error summarizing lecture materials: {e}", exc_info=True)
        return {
            "topic": topic,
            "summary": f"An error occurred while summarizing lecture materials: {str(e)}",
            "images": [],
            "audio_url": None
        }


def _extract_context_text(result: dict) -> str:
    """
    Extract context text from RAG chain result.
    
    Args:
        result: The result dictionary from RAG chain invocation, containing 'docs' field.
    
    Returns:
        A concatenated string of all document page_content from the retrieved documents.
    """
    if not isinstance(result, dict):
        return ""
    
    docs = result.get("docs", [])
    if not docs:
        return ""
    
    # Extract page_content from each document
    context_parts = []
    for doc in docs:
        if hasattr(doc, "page_content"):
            content = doc.page_content
            if content:
                context_parts.append(content)
        elif isinstance(doc, dict) and "page_content" in doc:
            content = doc["page_content"]
            if content:
                context_parts.append(content)
    
    return "\n\n".join(context_parts)


def _verify_summary_accuracy(
    summary: str,
    context_text: str,
    topic: str = ""
) -> dict:
    """
    Verify the accuracy of a summary by comparing it with the source context using ROUGE metrics.
    
    ROUGE (Recall-Oriented Understudy for Gisting Evaluation) measures:
    - ROUGE-1: Overlap of unigrams (single words) between summary and reference
    - ROUGE-2: Overlap of bigrams (word pairs) between summary and reference
    - ROUGE-L: Longest Common Subsequence (LCS) based similarity
    
    Args:
        summary: The generated summary text to evaluate.
        context_text: The source context/reference text to compare against.
        topic: Optional topic name for logging purposes.
    
    Returns:
        A dictionary containing:
        - 'rouge_1': ROUGE-1 scores (precision, recall, fmeasure)
        - 'rouge_2': ROUGE-2 scores (precision, recall, fmeasure)
        - 'rouge_l': ROUGE-L scores (precision, recall, fmeasure)
        - 'report': A formatted string report of the scores
    """
    try:
        # Try importing rouge_score with better error handling
        try:
            from rouge_score import rouge_scorer
        except ImportError as import_err:
            # Provide more detailed error information
            import sys
            logger.error(f"Failed to import rouge_score. Python path: {sys.executable}")
            logger.error(f"Python version: {sys.version}")
            logger.error(f"Import error details: {import_err}")
            raise ImportError(
                f"rouge-score package not found. Install it with: pip install rouge-score. "
                f"Current Python: {sys.executable}"
            )
        
        if not summary or not context_text:
            logger.warning(f"Empty summary or context for topic: {topic}")
            empty_result = {
                "precision": 0.0, "recall": 0.0, "fmeasure": 0.0,
                "precision_pct": 0.0, "recall_pct": 0.0, "fmeasure_pct": 0.0
            }
            return {
                "rouge_1": empty_result.copy(),
                "rouge_2": empty_result.copy(),
                "rouge_l": empty_result.copy(),
                "overall": {
                    "avg_fmeasure": 0.0,
                    "avg_fmeasure_pct": 0.0,
                    "accuracy_level": "N/A",
                    "recommendation": "Cannot compute ROUGE scores: empty summary or context"
                },
                "report": "Cannot compute ROUGE scores: empty summary or context"
            }
        
        # Initialize ROUGE scorer with all metrics
        scorer = rouge_scorer.RougeScorer(
            ['rouge1', 'rouge2', 'rougeL'],
            use_stemmer=True
        )
        
        # Compute ROUGE scores
        scores = scorer.score(context_text, summary)
        
        # Extract scores in a structured format
        rouge_1 = {
            "precision": scores['rouge1'].precision,
            "recall": scores['rouge1'].recall,
            "fmeasure": scores['rouge1'].fmeasure
        }
        
        rouge_2 = {
            "precision": scores['rouge2'].precision,
            "recall": scores['rouge2'].recall,
            "fmeasure": scores['rouge2'].fmeasure
        }
        
        rouge_l = {
            "precision": scores['rougeL'].precision,
            "recall": scores['rougeL'].recall,
            "fmeasure": scores['rougeL'].fmeasure
        }
        
        # Determine accuracy level and recommendation
        avg_fmeasure = (rouge_1['fmeasure'] + rouge_2['fmeasure'] + rouge_l['fmeasure']) / 3
        
        if avg_fmeasure >= 0.60:
            accuracy_level = "EXCELLENT"
            recommendation = "Summary is highly accurate and closely matches the source material."
            color_indicator = "✓"
        elif avg_fmeasure >= 0.45:
            accuracy_level = "GOOD"
            recommendation = "Summary is generally accurate but may benefit from minor improvements."
            color_indicator = "✓"
        elif avg_fmeasure >= 0.30:
            accuracy_level = "FAIR"
            recommendation = "Summary has moderate accuracy. Consider reviewing and improving key points."
            color_indicator = "⚠"
        else:
            accuracy_level = "POOR"
            recommendation = "Summary has low accuracy. Significant revision recommended - may contain hallucinations or missing key information."
            color_indicator = "✗"
        
        # Create a formatted report with percentages
        report = f"""
ROUGE Scores for topic: {topic or 'N/A'}
{'=' * 60}
ROUGE-1 (Unigram Overlap):
  Precision: {rouge_1['precision']:.4f} ({rouge_1['precision']*100:.2f}%)
  Recall:    {rouge_1['recall']:.4f} ({rouge_1['recall']*100:.2f}%)
  F-measure: {rouge_1['fmeasure']:.4f} ({rouge_1['fmeasure']*100:.2f}%)

ROUGE-2 (Bigram Overlap):
  Precision: {rouge_2['precision']:.4f} ({rouge_2['precision']*100:.2f}%)
  Recall:    {rouge_2['recall']:.4f} ({rouge_2['recall']*100:.2f}%)
  F-measure: {rouge_2['fmeasure']:.4f} ({rouge_2['fmeasure']*100:.2f}%)

ROUGE-L (Longest Common Subsequence):
  Precision: {rouge_l['precision']:.4f} ({rouge_l['precision']*100:.2f}%)
  Recall:    {rouge_l['recall']:.4f} ({rouge_l['recall']*100:.2f}%)
  F-measure: {rouge_l['fmeasure']:.4f} ({rouge_l['fmeasure']*100:.2f}%)

{'=' * 60}
ACCURACY ASSESSMENT:
  Overall F-measure (Average): {avg_fmeasure:.4f} ({avg_fmeasure*100:.2f}%)
  Accuracy Level: {color_indicator} {accuracy_level}
  
RECOMMENDATION:
  {recommendation}

RECOMMENDED ACCURACY THRESHOLDS:
  • Excellent: F-measure ≥ 60% (0.60) - High quality, ready to use
  • Good:      F-measure ≥ 45% (0.45) - Acceptable with minor review
  • Fair:      F-measure ≥ 30% (0.30) - Needs improvement
  • Poor:      F-measure < 30% (0.30) - Significant revision required
{'=' * 60}
        """.strip()
        
        logger.info(f"ROUGE scores computed for topic: {topic}")
        logger.debug(f"ROUGE-1 F-measure: {rouge_1['fmeasure']:.4f}, ROUGE-2 F-measure: {rouge_2['fmeasure']:.4f}, ROUGE-L F-measure: {rouge_l['fmeasure']:.4f}")
        
        return {
            "rouge_1": {
                **rouge_1,
                "precision_pct": rouge_1['precision'] * 100,
                "recall_pct": rouge_1['recall'] * 100,
                "fmeasure_pct": rouge_1['fmeasure'] * 100
            },
            "rouge_2": {
                **rouge_2,
                "precision_pct": rouge_2['precision'] * 100,
                "recall_pct": rouge_2['recall'] * 100,
                "fmeasure_pct": rouge_2['fmeasure'] * 100
            },
            "rouge_l": {
                **rouge_l,
                "precision_pct": rouge_l['precision'] * 100,
                "recall_pct": rouge_l['recall'] * 100,
                "fmeasure_pct": rouge_l['fmeasure'] * 100
            },
            "overall": {
                "avg_fmeasure": avg_fmeasure,
                "avg_fmeasure_pct": avg_fmeasure * 100,
                "accuracy_level": accuracy_level,
                "recommendation": recommendation
            },
            "report": report
        }
        
    except ImportError as import_err:
        import sys
        python_path = sys.executable
        error_msg = (
            f"ROUGE evaluation failed: rouge-score package not found.\n"
            f"Python interpreter: {python_path}\n"
            f"Error: {str(import_err)}\n"
            f"To fix: pip install rouge-score (or activate your virtual environment if using one)"
        )
        logger.error(error_msg)
        empty_result = {
            "precision": 0.0, "recall": 0.0, "fmeasure": 0.0,
            "precision_pct": 0.0, "recall_pct": 0.0, "fmeasure_pct": 0.0
        }
        return {
            "rouge_1": empty_result.copy(),
            "rouge_2": empty_result.copy(),
            "rouge_l": empty_result.copy(),
            "overall": {
                "avg_fmeasure": 0.0,
                "avg_fmeasure_pct": 0.0,
                "accuracy_level": "ERROR",
                "recommendation": error_msg
            },
            "report": error_msg
        }
    except Exception as e:
        logger.error(f"Error computing ROUGE scores: {e}", exc_info=True)
        empty_result = {
            "precision": 0.0, "recall": 0.0, "fmeasure": 0.0,
            "precision_pct": 0.0, "recall_pct": 0.0, "fmeasure_pct": 0.0
        }
        return {
            "rouge_1": empty_result.copy(),
            "rouge_2": empty_result.copy(),
            "rouge_l": empty_result.copy(),
            "overall": {
                "avg_fmeasure": 0.0,
                "avg_fmeasure_pct": 0.0,
                "accuracy_level": "ERROR",
                "recommendation": f"ROUGE evaluation failed: {str(e)}"
            },
            "report": f"ROUGE evaluation failed: {str(e)}"
        }


def verify_guidance_accuracy(
    guidance_text: str,
    assignment_topic: str = ""
) -> dict:
    """
    Verify the accuracy of CA guidance by comparing it with relevant lecture materials using ROUGE.
    
    This function:
    1. Extracts key topics/concepts from the guidance text
    2. Queries lecture materials for relevant context
    3. Compares guidance with retrieved context using ROUGE metrics
    
    Args:
        guidance_text: The generated CA guidance text to evaluate.
        assignment_topic: Optional topic or assignment description for better context retrieval.
    
    Returns:
        A dictionary containing:
        - 'rouge_1': ROUGE-1 scores (precision, recall, fmeasure)
        - 'rouge_2': ROUGE-2 scores (precision, recall, fmeasure)
        - 'rouge_l': ROUGE-L scores (precision, recall, fmeasure)
        - 'report': A formatted string report of the scores
        - 'context_retrieved': Boolean indicating if context was successfully retrieved
    """
    try:
        rag_chain = _get_rag_chain()
        
        if rag_chain is None:
            logger.warning("RAG chain not available for guidance verification")
            return {
                "rouge_1": {"precision": 0.0, "recall": 0.0, "fmeasure": 0.0},
                "rouge_2": {"precision": 0.0, "recall": 0.0, "fmeasure": 0.0},
                "rouge_l": {"precision": 0.0, "recall": 0.0, "fmeasure": 0.0},
                "report": "ROUGE evaluation failed: RAG system not available",
                "context_retrieved": False
            }
        
        # Create a query to retrieve relevant context from lecture materials
        # Use assignment topic if provided, otherwise extract keywords from guidance
        if assignment_topic:
            query = f"Provide detailed information about {assignment_topic} from lecture materials"
        else:
            # Extract first 200 characters as a query hint
            query_hint = guidance_text[:200].replace("\n", " ").strip()
            query = f"Lecture materials about: {query_hint}"
        
        # Retrieve relevant context
        result = rag_chain.invoke({"question": query})
        context_text = _extract_context_text(result)
        
        if not context_text:
            logger.warning("No context retrieved for guidance verification")
            return {
                "rouge_1": {"precision": 0.0, "recall": 0.0, "fmeasure": 0.0},
                "rouge_2": {"precision": 0.0, "recall": 0.0, "fmeasure": 0.0},
                "rouge_l": {"precision": 0.0, "recall": 0.0, "fmeasure": 0.0},
                "report": "ROUGE evaluation failed: No relevant context found in lecture materials",
                "context_retrieved": False
            }
        
        # Use the existing verification function
        verification_result = _verify_summary_accuracy(
            summary=guidance_text,
            context_text=context_text,
            topic=f"CA Guidance: {assignment_topic or 'General'}"
        )
        
        verification_result["context_retrieved"] = True
        return verification_result
        
    except Exception as e:
        logger.error(f"Error verifying guidance accuracy: {e}", exc_info=True)
        return {
            "rouge_1": {"precision": 0.0, "recall": 0.0, "fmeasure": 0.0},
            "rouge_2": {"precision": 0.0, "recall": 0.0, "fmeasure": 0.0},
            "rouge_l": {"precision": 0.0, "recall": 0.0, "fmeasure": 0.0},
            "report": f"ROUGE evaluation failed: {str(e)}",
            "context_retrieved": False
        }