"""
Proxies /guidance/ -> academic-guidance, /papers/ -> model-paper-generation, /mcq/ -> mcq-study-plan.
Run as a module:
    python -m uvicorn main:app --host 0.0.0.0 --port 7777
or directly:
    python main.py
"""
import os
import asyncio
import json
import time
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import Response, JSONResponse, StreamingResponse
import httpx

GUIDANCE_TARGET = os.getenv("GUIDANCE_TARGET", "http://20.196.136.226:8081")
PAPERS_TARGET = os.getenv("PAPERS_TARGET", "http://127.0.0.1:8000")
ESSAY_TARGET = os.getenv("ESSAY_TARGET", "http://127.0.0.1:8002")
MCQ_TARGET = os.getenv("MCQ_TARGET", "http://127.0.0.1:8003")
PORT = int(os.getenv("PORT", "7777"))

DEFAULT_ALLOWED_ORIGINS = [
    "http://20.196.136.226:5173",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
]
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOWED_ORIGINS", ",".join(DEFAULT_ALLOWED_ORIGINS)).split(",")
    if origin.strip()
]

app = FastAPI(title="Research Project Gateway (local)")

# Headers not forwarded (set per-request)
FORWARD_SKIP_HEADERS = {"host", "connection", "content-length"}

# Paper generation can take 15–30+ min (preprocessing + AI). Use longer timeout for /papers/.
DEFAULT_PROXY_TIMEOUT = float(os.getenv("DEFAULT_PROXY_TIMEOUT", "86400"))
PAPERS_PROXY_TIMEOUT = float(os.getenv("PAPERS_PROXY_TIMEOUT", "86400"))  # 24 hours
# Guidance (CrewAI + tools) can exceed 5 minutes on slow networks or large PDFs.
GUIDANCE_PROXY_TIMEOUT = float(os.getenv("GUIDANCE_PROXY_TIMEOUT", "86400"))  # 24 hours
# MCQ "Run Analysis" can be slow (many PDFs + embeddings + graph). Default higher than generic proxy.
MCQ_PROXY_TIMEOUT = float(os.getenv("MCQ_PROXY_TIMEOUT", "86400"))
STREAM_HEARTBEAT_SECONDS = float(os.getenv("STREAM_HEARTBEAT_SECONDS", "15"))
STREAM_HEARTBEAT_CHUNK = (b" " * 1024) + b"\n"


def _cors_headers(request: Request) -> dict[str, str]:
    origin = request.headers.get("origin")
    if origin not in ALLOWED_ORIGINS:
        return {}
    return {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Allow-Methods": "GET, POST, PUT, PATCH, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Authorization,Content-Type,Accept,Origin,User-Agent,Referer,Host,Cache-Control,Pragma,X-Requested-With",
        "Access-Control-Max-Age": "1728000",
        "Vary": "Origin",
    }


@app.middleware("http")
async def add_cors_headers(request: Request, call_next):
    if request.method == "OPTIONS":
        return Response(status_code=204, headers=_cors_headers(request))

    response = await call_next(request)
    for name, value in _cors_headers(request).items():
        response.headers[name] = value
    return response


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
    if request.method == "POST" and path == "protected/run-guidance":
        return await _proxy_with_keepalive(request, GUIDANCE_TARGET, "guidance", path, timeout=GUIDANCE_PROXY_TIMEOUT)
    return await _proxy(request, GUIDANCE_TARGET, "guidance", path, timeout=GUIDANCE_PROXY_TIMEOUT)


@app.api_route("/papers/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_papers(request: Request, path: str):
    if request.method == "POST" and path in {"model-paper/generate-paper", "model-paper/generate-paper-a"}:
        return await _proxy_with_keepalive(request, PAPERS_TARGET, "papers", path, timeout=PAPERS_PROXY_TIMEOUT)
    return await _proxy(request, PAPERS_TARGET, "papers", path, timeout=PAPERS_PROXY_TIMEOUT)


@app.api_route("/essay/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_essay(request: Request, path: str):
    return await _proxy(request, ESSAY_TARGET, "essay", path)


@app.api_route("/mcq/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def proxy_mcq(request: Request, path: str):
    return await _proxy(request, MCQ_TARGET, "mcq", path, timeout=MCQ_PROXY_TIMEOUT)


async def _proxy(request: Request, target_base: str, prefix: str, path: str, timeout: float = None):
    """Forward request to target service and return response."""
    if timeout is None:
        timeout = DEFAULT_PROXY_TIMEOUT
    started_at = time.perf_counter()
    url, headers, body = await _build_upstream_request(request, target_base, prefix, path)

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            print(f"[gateway] -> {request.method} /{prefix}/{path} target={url} timeout={timeout}s", flush=True)
            resp = await client.request(
                request.method,
                url,
                headers=headers,
                content=body,
            )
            elapsed = time.perf_counter() - started_at
            print(
                f"[gateway] <- {request.method} /{prefix}/{path} "
                f"status={resp.status_code} bytes={len(resp.content)} elapsed={elapsed:.1f}s",
                flush=True,
            )
        except httpx.ConnectError as e:
            return JSONResponse(
                status_code=502,
                content={"detail": f"Backend unreachable: {target_base}", "error": str(e)},
                headers=_cors_headers(request),
            )
        except httpx.TimeoutException as e:
            return JSONResponse(
                status_code=504,
                content={"detail": f"{prefix} backend timed out after {timeout} seconds. The job may still be running in its service terminal.", "error": str(e)},
                headers=_cors_headers(request),
            )
        except Exception as e:
            return JSONResponse(status_code=502, content={"detail": str(e)}, headers=_cors_headers(request))

    # Forward response (drop hop-by-hop and upstream CORS headers).
    # The gateway/nginx layer owns CORS so the browser sees one consistent policy.
    skip = {
        "transfer-encoding",
        "connection",
        "content-encoding",
        "access-control-allow-origin",
        "access-control-allow-credentials",
        "access-control-allow-methods",
        "access-control-allow-headers",
        "access-control-expose-headers",
        "access-control-max-age",
    }
    out_headers = {k: v for k, v in resp.headers.items() if k.lower() not in skip}
    out_headers.update(_cors_headers(request))
    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=out_headers,
    )


async def _build_upstream_request(request: Request, target_base: str, prefix: str, path: str):
    url = f"{target_base.rstrip('/')}/{path}"
    if request.url.query:
        url = f"{url}?{request.url.query}"

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

    return url, headers, body


async def _proxy_with_keepalive(request: Request, target_base: str, prefix: str, path: str, timeout: float = None):
    """Keep browser/nginx connections alive while a long backend job runs.

    JSON permits leading whitespace, so the stream sends whitespace heartbeats first
    and the real backend JSON as the final chunk.
    """
    if timeout is None:
        timeout = DEFAULT_PROXY_TIMEOUT
    started_at = time.perf_counter()
    url, headers, body = await _build_upstream_request(request, target_base, prefix, path)
    cors_headers = _cors_headers(request)
    response_headers = {
        **cors_headers,
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
        "X-RP-Gateway-Keepalive": "streaming-json",
    }

    async def run_backend():
        async with httpx.AsyncClient(timeout=timeout) as client:
            print(f"[gateway-stream] -> {request.method} /{prefix}/{path} target={url} timeout={timeout}s", flush=True)
            return await client.request(request.method, url, headers=headers, content=body)

    async def stream_json():
        task = asyncio.create_task(run_backend())
        yield STREAM_HEARTBEAT_CHUNK

        while not task.done():
            await asyncio.sleep(STREAM_HEARTBEAT_SECONDS)
            if not task.done():
                yield STREAM_HEARTBEAT_CHUNK

        try:
            resp = await task
            elapsed = time.perf_counter() - started_at
            print(
                f"[gateway-stream] <- {request.method} /{prefix}/{path} "
                f"status={resp.status_code} bytes={len(resp.content)} elapsed={elapsed:.1f}s",
                flush=True,
            )
            if resp.content:
                yield resp.content
            else:
                yield json.dumps({"status": "success", "detail": "Backend returned an empty response."}).encode("utf-8")
        except httpx.ConnectError as e:
            yield json.dumps({"status": "error", "detail": f"Backend unreachable: {target_base}", "error": str(e)}).encode("utf-8")
        except httpx.TimeoutException as e:
            yield json.dumps({"status": "error", "detail": f"{prefix} backend timed out after {timeout} seconds.", "error": str(e)}).encode("utf-8")
        except Exception as e:
            yield json.dumps({"status": "error", "detail": str(e)}).encode("utf-8")

    return StreamingResponse(
        stream_json(),
        status_code=200,
        media_type="application/json",
        headers=response_headers,
    )


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=PORT,
        reload=False,
    )
