from fastapi import APIRouter



from app.api.routes.health import router as health_router

from app.api.routes.sessions import router as sessions_router

from app.api.routes.questions import router as questions_router

from app.api.routes.answers import router as answers_router

from app.api.routes.stats import router as stats_router

from app.api.routes.analytics import router as analytics_router

from app.api.routes.practice import router as practice_router



router = APIRouter()



router.include_router(health_router)

router.include_router(sessions_router)

router.include_router(questions_router)

router.include_router(answers_router)

router.include_router(stats_router)

router.include_router(analytics_router)

router.include_router(practice_router, prefix="/api", tags=["practice"])

