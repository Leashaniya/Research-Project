"""
Proxies /guidance/ -> academic-guidance:8000, /papers/ -> model-paper-generation:8001.
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

GUIDANCE_TARGET = os.getenv("GUIDANCE_TARGET", "http://127.0.0.1:8001")
PAPERS_TARGET = os.getenv("PAPERS_TARGET", "http://127.0.0.1:8000")
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


@app.get("/health")
def health():
    return JSONResponse(content={"status": "ok", "service": "gateway"})


@app.get("/")
def root():
    return JSONResponse(
        content={
            "gateway": "Research Project API (local)",
            "routes": {"health": "/health", "guidance": "/guidance/", "papers": "/papers/"},
        }
    )


@app.api_route("/guidance/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_guidance(request: Request, path: str):
    return await _proxy(request, GUIDANCE_TARGET, "guidance", path)


@app.api_route("/papers/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_papers(request: Request, path: str):
    return await _proxy(request, PAPERS_TARGET, "papers", path)


async def _proxy(request: Request, target_base: str, prefix: str, path: str):
    """Forward request to target service and return response."""
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

    async with httpx.AsyncClient(timeout=300.0) as client:
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