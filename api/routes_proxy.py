import httpx
from fastapi import APIRouter, Request, Response
from api.config import COMFYUI_URL, OLLAMA_URL

router = APIRouter()

async def _async_proxy(target_url: str, request: Request):
    params = dict(request.query_params)
    body = await request.body()
    headers = {k: v for k, v in request.headers.items() if k.lower() not in ["host", "content-length"]}
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.request(
                method=request.method, url=target_url, params=params,
                headers=headers, content=body, follow_redirects=False
            )
            resp_headers = {}
            for k, v in resp.headers.items():
                if k.lower() not in ["content-encoding", "transfer-encoding", "content-length", "access-control-allow-origin"]:
                    resp_headers[k] = v
            return Response(content=resp.content, status_code=resp.status_code, headers=resp_headers)
        except Exception as e:
            return Response(content=f"Proxy error: {e}".encode("utf-8"), status_code=502)

@router.api_route("/api/huggingface/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def proxy_huggingface(path: str, request: Request):
    return await _async_proxy(f"https://huggingface.co/api/{path}", request)

@router.api_route("/api/civitai/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def proxy_civitai(path: str, request: Request):
    return await _async_proxy(f"https://civitai.red/api/{path}", request)

@router.api_route("/api/comfyui/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def proxy_comfyui(path: str, request: Request):
    return await _async_proxy(f"{COMFYUI_URL}/{path}", request)

@router.api_route("/api/ollama/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def proxy_ollama(path: str, request: Request):
    return await _async_proxy(f"{OLLAMA_URL}/{path}", request)
