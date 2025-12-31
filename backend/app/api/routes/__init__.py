# from fastapi import APIRouter
# from .endpoints import past_papers, lecture_slides, pipeline, model_paper

# router = APIRouter()

# router.include_router(past_papers.router, prefix="/past-papers", tags=["Past Papers"])
# router.include_router(lecture_slides.router, prefix="/lecture-slides", tags=["Lecture Slides"])
# router.include_router(pipeline.router, prefix="/pipeline", tags=["Pipeline"])
# router.include_router(model_paper.router, prefix="/model-paper", tags=["Model Paper"])

from fastapi import APIRouter
from .endpoints import past_papers, lecture_slides, model_paper

router = APIRouter()
router.include_router(past_papers.router, prefix="/past-papers", tags=["Past Papers"])
router.include_router(lecture_slides.router, prefix="/lecture-slides", tags=["Lecture Slides"])
router.include_router(model_paper.router, prefix="/model-paper", tags=["Model Paper"])
