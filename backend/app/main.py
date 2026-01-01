from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from app.api.routes import router
from app.core.paths import PAST_PAPERS_DIR, SLIDES_DIR, OUTPUTS_DIR
import os

app = FastAPI()

@app.on_event("startup")
async def startup_event():
    os.makedirs(PAST_PAPERS_DIR, exist_ok=True)
    os.makedirs(SLIDES_DIR, exist_ok=True)
    os.makedirs(OUTPUTS_DIR, exist_ok=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

@app.get("/")
def root():
    return RedirectResponse(url="/docs")
