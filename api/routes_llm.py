from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from typing import List, Optional
import httpx
import json
import logging
from api.auth import require_auth, _get_client_ip, _is_trusted_client_ip, bearer_scheme
from api.config import NGC_API_KEY

logger = logging.getLogger("vaultwares.api")
router = APIRouter()

class ChatMessage(BaseModel):
    role: str
    content: str

class NemotronRequest(BaseModel):
    messages: List[ChatMessage]
    temperature: Optional[float] = 1.0
    top_p: Optional[float] = 0.95
    max_tokens: Optional[int] = 16384
    stream: Optional[bool] = True
    enable_thinking: Optional[bool] = True
    reasoning_budget: Optional[int] = 16384

async def require_auth_or_tailnet(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme)
):
    client_ip = _get_client_ip(request)
    if _is_trusted_client_ip(client_ip):
        return {"kind": "tailnet", "ip": client_ip}
    
    # Call standard require_auth for non-tailnet requests
    return await require_auth(request, credentials)

async def stream_nvidia_nemotron(payload: dict):
    async with httpx.AsyncClient() as client:
        try:
            async with client.stream(
                "POST",
                "https://integrate.api.nvidia.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {NGC_API_KEY}",
                    "Content-Type": "application/json"
                },
                json=payload,
                timeout=120.0
            ) as r:
                if r.status_code != 200:
                    error_text = await r.aread()
                    logger.error(f"NVIDIA API stream error: {r.status_code} - {error_text.decode('utf-8')}")
                    yield f"data: {json.dumps({'error': f'NVIDIA API returned status {r.status_code}'})}\n\n"
                    return
                
                async for line in r.aiter_lines():
                    if line.strip():
                        yield f"{line}\n"
        except Exception as e:
            logger.exception("Error streaming from NVIDIA API")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

@router.post("/api/llm/nemotron")
async def chat_nemotron(
    req: NemotronRequest,
    principal=Depends(require_auth_or_tailnet)
):
    if not NGC_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="NGC_API_KEY is not configured on the API server."
        )

    # Build the payload for the NVIDIA API
    payload = {
        "model": "nvidia/nemotron-3-ultra-550b-a55b",
        "messages": [msg.model_dump() for msg in req.messages],
        "temperature": req.temperature,
        "top_p": req.top_p,
        "max_tokens": req.max_tokens,
        "stream": req.stream,
        "chat_template_kwargs": {"enable_thinking": req.enable_thinking},
        "reasoning_budget": req.reasoning_budget
    }

    if req.stream:
        return StreamingResponse(
            stream_nvidia_nemotron(payload),
            media_type="text/event-stream"
        )
    else:
        async with httpx.AsyncClient() as client:
            try:
                r = await client.post(
                    "https://integrate.api.nvidia.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {NGC_API_KEY}",
                        "Content-Type": "application/json"
                    },
                    json=payload,
                    timeout=120.0
                )
                if r.status_code != 200:
                    logger.error(f"NVIDIA API error: {r.status_code} - {r.text}")
                    raise HTTPException(
                        status_code=r.status_code,
                        detail=f"NVIDIA API returned error: {r.text}"
                    )
                return r.json()
            except Exception as e:
                logger.exception("Error calling NVIDIA API")
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to communicate with NVIDIA: {str(e)}"
                )

@router.get("/api/llm/nemotron")
async def check_nemotron_auth(
    principal=Depends(require_auth_or_tailnet)
):
    return {"status": "authenticated", "principal_kind": principal.get("kind")}

