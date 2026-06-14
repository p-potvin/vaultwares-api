import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter()
logger = logging.getLogger("vaultwares.api")

# In-memory storage for hosts and routes (consider moving to DB in production)
_HOSTS_DB = [
    {"id": "katfile", "name": "Katfile", "baseDomain": "katfile.com", "priority": 100},
    {"id": "keep2share", "name": "Keep2Share", "baseDomain": "keep2share.cc", "priority": 100},
    {"id": "k2s", "name": "K2S", "baseDomain": "k2s.cc", "priority": 100},
    {"id": "fileboom", "name": "FileBoom", "baseDomain": "fileboom.me", "priority": 100},
    {"id": "fboom", "name": "FBoom", "baseDomain": "fboom.me", "priority": 100},
    {"id": "rapidgator", "name": "RapidGator", "baseDomain": "rapidgator.net", "priority": 100},
    {"id": "rgto", "name": "RG.to", "baseDomain": "rg.to", "priority": 100},
]

_ROUTES_DB = {}

# Pydantic models
class HostConfig(BaseModel):
    id: str
    name: str
    baseDomain: str
    priority: int = 100

class QuickCreateRequest(BaseModel):
    title: str
    contentId: str
    slug: str
    hostId: str
    remoteUrl: str
    priority: int = 100

class QuickCreateResponse(BaseModel):
    slug: str
    id: str
    hostId: str
    remoteUrl: str
    shortUrl: str


@router.get("/api/hosts", response_model=List[HostConfig])
async def get_hosts():
    """Get all configured file hosts for link sharing"""
    logger.info("Link Sharing: Fetching hosts list")
    return _HOSTS_DB


@router.post("/api/routes/quick-create", response_model=QuickCreateResponse)
async def quick_create_route(
    request: QuickCreateRequest,
    authorization: Optional[str] = Header(None)
):
    """Create a quick link sharing route"""
    
    # Validate API key (matching telethon_link_resolver.py line 878)
    if authorization != "Bearer dev-secret-key-123":
        logger.warning(f"Link Sharing: Unauthorized access attempt")
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    # Validate host exists
    host_ids = [h["id"] for h in _HOSTS_DB]
    if request.hostId not in host_ids:
        logger.error(f"Link Sharing: Invalid hostId: {request.hostId}")
        raise HTTPException(status_code=400, detail=f"Invalid hostId: {request.hostId}")
    
    # Generate unique ID
    route_id = str(uuid.uuid4())
    
    # Store the route
    route_data = {
        "id": route_id,
        "title": request.title,
        "contentId": request.contentId,
        "slug": request.slug,
        "hostId": request.hostId,
        "remoteUrl": request.remoteUrl,
        "priority": request.priority,
        "created_at": __import__("time").time()
    }
    _ROUTES_DB[route_id] = route_data
    
    logger.info(f"Link Sharing: Created route {route_id} for {request.title} -> {request.remoteUrl}")
    
    # Return response with short URL format
    return {
        "slug": request.slug,
        "id": route_id,
        "hostId": request.hostId,
        "remoteUrl": request.remoteUrl,
        "shortUrl": f"http://100.67.25.118:9001/f/{request.slug}"
    }
