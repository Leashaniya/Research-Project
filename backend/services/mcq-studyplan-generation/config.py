import os

# Folder paths
LECTURE_SLIDES_FOLDER = "Lecture_slides"
QUESTIONS_FOLDER = "Questions"

# Output files
OUTPUT_HTML = "lecture_recommendation_graph.html"
STUDY_PLAN_OUTPUT = "study_plan.csv"
SUMMARY_OUTPUT = "lecture_summary.csv"

# Processing parameters
N_TOPICS = 6
TOP_KEYWORDS_PER_TOPIC = 5
SIMILARITY_THRESHOLD = 0.30
EMBED_MODEL_NAME = "all-MiniLM-L6-v2"
MAX_SENTENCES_PER_LECTURE = 100

# Study plan parameters
DEFAULT_STUDY_HOURS_PER_DAY = 2
DEFAULT_TOTAL_STUDY_DAYS = 7

# OpenAI configuration (keep for graph enrichment only) - use env
import os
OPENAI_API_KEY = "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"