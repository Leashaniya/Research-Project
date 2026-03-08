"""
Proxies /guidance/ -> academic-guidance, /papers/ -> model-paper-generation, /mcq/ -> mcq-study-plan.
Run as a module:
    python -m uvicorn main:app --host 0.0.0.0 --port 80
or directly:
    python main.py
"""
import os
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx

GUIDANCE_TARGET = os.getenv("GUIDANCE_TARGET", "http://127.0.0.1:8081")
PAPERS_TARGET = os.getenv("PAPERS_TARGET", "http://127.0.0.1:8000")
ESSAY_TARGET = os.getenv("ESSAY_TARGET", "http://127.0.0.1:8002")
MCQ_TARGET = os.getenv("MCQ_TARGET", "http://127.0.0.1:8003")
PORT = int(os.getenv("PORT", "80"))

app = FastAPI(title="Research Project Gateway (local)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Headers not forwarded (set per-request)
FORWARD_SKIP_HEADERS = {"host", "connection", "content-length"}

# Paper generation can take 15–30+ min (preprocessing + AI). Use longer timeout for /papers/.
DEFAULT_PROXY_TIMEOUT = 300.0
PAPERS_PROXY_TIMEOUT = float(os.getenv("PAPERS_PROXY_TIMEOUT", "1800"))  # 30 min


@app.get("/health")
def health():
    return JSONResponse(content={"status": "ok", "service": "gateway"})


@app.get("/")
def root():
    return JSONResponse(
        content={
            "gateway": "Research Project API (local)",
            "routes": {"health": "/health", "guidance": "/guidance/", "papers": "/papers/", "essay": "/essay/", "mcq": "/mcq/"},
        }
    )


@app.api_route("/guidance/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_guidance(request: Request, path: str):
    return await _proxy(request, GUIDANCE_TARGET, "guidance", path)


@app.api_route("/papers/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_papers(request: Request, path: str):
    return await _proxy(request, PAPERS_TARGET, "papers", path, timeout=PAPERS_PROXY_TIMEOUT)


@app.api_route("/essay/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_essay(request: Request, path: str):
    return await _proxy(request, ESSAY_TARGET, "essay", path)


@app.api_route("/mcq/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_mcq(request: Request, path: str):
    return await _proxy(request, MCQ_TARGET, "mcq", path)


async def _proxy(request: Request, target_base: str, prefix: str, path: str, timeout: float = None):
    """Forward request to target service and return response."""
    if timeout is None:
        timeout = DEFAULT_PROXY_TIMEOUT
    url = f"{target_base.rstrip('/')}/{path}"
    if request.url.query:
        url = f"{url}?{request.url.query}"

    # Forward request headers (excluding hop-by-hop)
    headers = {}
    for name, value in request.headers.items():
        if name.lower() not in FORWARD_SKIP_HEADERS:
            headers[name] = value
    headers["X-Forwarded-Proto"] = request.url.scheme
    headers["X-Forwarded-Prefix"] = f"/{prefix}"
    if request.client:
        headers["X-Forwarded-For"] = request.client.host

    try:
        body = await request.body()
    except Exception:
        body = b""

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.request(
                request.method,
                url,
                headers=headers,
                content=body,
            )
        except httpx.ConnectError as e:
            return JSONResponse(
                status_code=502,
                content={"detail": f"Backend unreachable: {target_base}", "error": str(e)},
            )
        except httpx.TimeoutException as e:
            return JSONResponse(
                status_code=504,
                content={"detail": "Paper generation timed out. The pipeline can take 15–30+ minutes. Try again or run it from the backend terminal (run_full_pipeline.py).", "error": str(e)},
            )
        except Exception as e:
            return JSONResponse(status_code=502, content={"detail": str(e)})

    # Forward response (drop hop-by-hop)
    skip = {"transfer-encoding", "connection", "content-encoding"}
    out_headers = {k: v for k, v in resp.headers.items() if k.lower() not in skip}
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=out_headers,
    )


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=PORT,
        reload=False,
    )