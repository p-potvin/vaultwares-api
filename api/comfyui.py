import httpx
import time
import secrets
import asyncio
import logging
import json
from jose import jwt, JWTError
from typing import List, Optional
from api.config import (
    COMFYUI_URL, COMFYUI_PROMPT_TIMEOUT_SECONDS, COMFYUI_URL_TOKEN_TTL_SECONDS,
    JWT_SECRET, JWT_ISSUER
)
from fastapi import HTTPException, Response

logger = logging.getLogger("vaultwares.api")

def _sign_comfyui_image_token(filename: str, subfolder: str, type_: str) -> str:
    now = int(time.time())
    claims = {
        "iss": JWT_ISSUER,
        "aud": "comfyui-image",
        "iat": now,
        "nbf": now,
        "exp": now + COMFYUI_URL_TOKEN_TTL_SECONDS,
        "fn": filename,
        "sub_": subfolder,
        "tp": type_,
    }
    return jwt.encode(claims, JWT_SECRET, algorithm="HS256")

def _verify_comfyui_image_token(token: str) -> dict:
    try:
        claims = jwt.decode(
            token, JWT_SECRET, algorithms=["HS256"],
            audience="comfyui-image", issuer=JWT_ISSUER,
        )
    except JWTError as e:
        raise HTTPException(status_code=403, detail=f"Invalid image token: {e}")
    return claims

async def _comfyui_ws_listener(
    client_id: str,
    prompt_id: str,
    progress_cb,
    cancel_event: asyncio.Event,
    done_event: asyncio.Event,
) -> None:
    if progress_cb is None: return
    ws_url = COMFYUI_URL.replace("http://", "ws://").replace("https://", "wss://")
    url = f"{ws_url}/ws?clientId={client_id}"
    try:
        import websockets
        async with websockets.connect(url, max_size=None, ping_interval=20) as ws:
            while not done_event.is_set() and not cancel_event.is_set():
                try: raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                except asyncio.TimeoutError: continue
                except Exception: return
                if not isinstance(raw, (str, bytes)): continue
                if isinstance(raw, bytes): continue
                try: msg = json.loads(raw)
                except: continue
                kind = msg.get("type")
                data = msg.get("data") or {}
                if not isinstance(data, dict): continue
                if data.get("prompt_id") and data["prompt_id"] != prompt_id: continue
                if kind in ("execution_start", "execution_cached", "executing", "progress", "executed", "execution_error", "execution_success"):
                    try: progress_cb({"kind": kind, **data})
                    except: pass
    except Exception as exc:
        logger.debug(f"ComfyUI ws listener for {prompt_id} ended: {exc}")

async def _execute_comfyui_graph(graph: dict, progress_cb=None, cancel_event: asyncio.Event | None = None) -> dict:
    client_id = secrets.token_hex(8)
    deadline = time.time() + COMFYUI_PROMPT_TIMEOUT_SECONDS
    cancel_event = cancel_event or asyncio.Event()
    done_event = asyncio.Event()

    async with httpx.AsyncClient(timeout=COMFYUI_PROMPT_TIMEOUT_SECONDS) as client:
        try:
            r = await client.post(f"{COMFYUI_URL}/prompt", json={"prompt": graph, "client_id": client_id})
        except httpx.RequestError as e:
            raise RuntimeError(f"ComfyUI POST /prompt failed: {e}") from e
        if r.status_code >= 400:
            raise RuntimeError(f"ComfyUI /prompt -> {r.status_code}: {r.text[:300]}")
        submit = r.json()
        prompt_id = submit.get("prompt_id")
        if not prompt_id: raise RuntimeError(f"ComfyUI didn't return prompt_id: {submit}")

        if progress_cb:
            try: progress_cb({"kind": "submitted", "prompt_id": prompt_id})
            except: pass

        listener_task = asyncio.create_task(_comfyui_ws_listener(client_id, prompt_id, progress_cb, cancel_event, done_event))
        try:
            while time.time() < deadline:
                if cancel_event.is_set():
                    try: await client.post(f"{COMFYUI_URL}/interrupt", timeout=5.0)
                    except: pass
                    raise RuntimeError("canceled")

                await asyncio.sleep(1.5)
                try: h = await client.get(f"{COMFYUI_URL}/history/{prompt_id}")
                except httpx.RequestError: continue
                if h.status_code != 200: continue
                history = h.json()
                entry = history.get(prompt_id)
                if not entry: continue
                status = entry.get("status", {})
                status_str = status.get("status_str")
                if status_str == "error":
                    raise RuntimeError(f"ComfyUI workflow errored: {status.get('messages', [])}")
                if status.get("completed") or status_str == "success":
                    outputs = entry.get("outputs", {})
                    image_refs = []
                    for node_out in outputs.values():
                        if not isinstance(node_out, dict): continue
                        for img in node_out.get("images") or []:
                            image_refs.append({"filename": img.get("filename"), "subfolder": img.get("subfolder", ""), "type": img.get("type", "output")})
                    if not image_refs: raise RuntimeError("ComfyUI workflow completed but produced no images")

                    image_urls = []
                    for img in image_refs:
                        token = _sign_comfyui_image_token(img["filename"], img.get("subfolder", ""), img.get("type", "output"))
                        image_urls.append(f"/api/comfyui-image/{token}")
                    return {"image_url": image_urls[0], "image_urls": image_urls, "prompt_id": prompt_id, "images": image_refs, "summary": f"Generated {len(image_refs)} image(s) via ComfyUI"}
        finally:
            done_event.set()
            try: await asyncio.wait_for(listener_task, timeout=2.0)
            except: listener_task.cancel()
    raise RuntimeError(f"ComfyUI prompt {prompt_id} did not complete within {COMFYUI_PROMPT_TIMEOUT_SECONDS}s")
