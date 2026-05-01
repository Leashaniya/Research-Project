"""MCQ API routes - all under /api for React mcqApi compatibility."""
from fastapi import APIRouter
from .endpoints import dashboard, study_plan, quiz, graph, metrics

router = APIRouter(prefix="/api")

# Dashboard: /api/dashboard/
router.include_router(dashboard.router, prefix="/dashboard", tags=["Dashboard"])
# Study plan: /api/study-plan/
router.include_router(study_plan.router, prefix="/study-plan", tags=["Study Plan"])
# Adaptive plan: /api/adaptive-plan/generate
router.include_router(study_plan.router_adaptive, prefix="/adaptive-plan", tags=["Adaptive Plan"])
# Priority questions: /api/priority-questions (GET)
router.include_router(quiz.router, prefix="/priority-questions", tags=["Priority Questions"])
# Quiz submit: /api/quiz/submit (POST)
router.include_router(quiz.router_quiz, prefix="/quiz", tags=["Quiz"])
# Graph: /api/graph/
router.include_router(graph.router, prefix="/graph", tags=["Graph"])
# Weak topic RAG summary: /api/weak-topic-summary
router.include_router(graph.router_weak, prefix="", tags=["Graph"])
# Metrics: /api/metrics/evaluation
router.include_router(metrics.router, prefix="/metrics", tags=["Metrics"])
