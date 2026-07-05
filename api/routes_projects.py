import logging
import httpx
import os
import subprocess
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from db import ProjectAlias

logger = logging.getLogger("vaultwares.projects")
router = APIRouter(prefix="/projects", tags=["projects"])

class ProjectAliasResponse(BaseModel):
    canonical: str
    repoId: Optional[str]
    owner: Optional[str]
    isPrivate: bool
    aliases: List[str]
    previousRemote: Optional[str]
    newRemote: Optional[str]
    notes: Optional[str]
    isDeleted: bool
    isFork: bool

@router.get("/aliases", response_model=List[ProjectAliasResponse])
async def get_project_aliases():
    """
    Returns the list of all project aliases, including forks and metadata.
    Used by vault-monitor and agent-ledger.
    """
    aliases = await ProjectAlias.all().order_by("canonical")
    return [
        ProjectAliasResponse(
            canonical=a.canonical,
            repoId=a.repoId,
            owner=a.owner,
            isPrivate=a.isPrivate,
            aliases=a.aliases if a.aliases else [],
            previousRemote=a.previousRemote,
            newRemote=a.newRemote,
            notes=a.notes,
            isDeleted=a.isDeleted,
            isFork=a.isFork,
        )
        for a in aliases
    ]

@router.post("/sync-github")
async def sync_github_projects():
    """
    Polls GitHub using httpx to discover new repositories, detect renames,
    and update project statuses in the database.
    """
    token = os.environ.get("GITHUB_PAT", "").strip()
    if not token:
        logger.warning("No GITHUB_PAT provided, trying local gh CLI as fallback...")
        try:
            result = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True)
            token = result.stdout.strip()
        except Exception:
            raise HTTPException(status_code=401, detail="GITHUB_PAT environment variable is required on VPS")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }

    targets = [
        {"name": "p-potvin", "type": "users"},
        {"name": "Prom-King", "type": "orgs"},
        {"name": "VaultWares", "type": "orgs"}
    ]

    fetched_repos = []
    
    async with httpx.AsyncClient() as client:
        for target in targets:
            url = f"https://api.github.com/{target['type']}/{target['name']}/repos?per_page=100"
            page = 1
            while True:
                response = await client.get(f"{url}&page={page}", headers=headers)
                if response.status_code != 200:
                    logger.error(f"Failed to fetch {target['name']}: {response.text}")
                    break
                
                repos = response.json()
                if not repos:
                    break
                    
                fetched_repos.extend(repos)
                page += 1

    fetched_map = {r["node_id"]: r for r in fetched_repos}
    existing_projects = await ProjectAlias.all()
    existing_repo_ids = {p.repoId: p for p in existing_projects if p.repoId}
    
    updates_made = 0
    new_added = 0
    now = datetime.now()
    
    for repo in fetched_repos:
        repo_id = repo["node_id"]
        full_name = repo["full_name"]
        name = repo["name"]
        owner = repo["owner"]["login"]
        is_private = repo["private"]
        is_archived = repo["archived"]
        is_fork = repo["fork"]

        if repo_id in existing_repo_ids:
            existing = existing_repo_ids[repo_id]
            needs_update = False

            if existing.newRemote != full_name:
                logger.info(f"Repository {existing.canonical} renamed to {full_name}")
                
                aliases = existing.aliases or []
                if not isinstance(aliases, list):
                    aliases = []
                    
                if existing.newRemote and existing.newRemote not in aliases:
                    aliases.append(existing.newRemote)
                if existing.canonical and existing.canonical not in aliases and existing.canonical != name:
                    aliases.append(existing.canonical)
                
                existing.aliases = aliases
                existing.previousRemote = existing.newRemote
                existing.newRemote = full_name
                existing.canonical = name
                existing.renamedAt = now
                needs_update = True
                
            if existing.isPrivate != is_private or existing.owner != owner or existing.isDeleted != is_archived:
                existing.isPrivate = is_private
                existing.owner = owner
                existing.isDeleted = is_archived
                if is_archived and not existing.deletedAt:
                    existing.deletedAt = now
                elif not is_archived:
                    existing.deletedAt = None
                needs_update = True
                
            if needs_update:
                await existing.save()
                updates_made += 1
        else:
            canonical_name = name
            clash = await ProjectAlias.get_or_none(canonical=canonical_name)
            if clash:
                canonical_name = full_name
                
            logger.info(f"Adding new repository: {canonical_name}")
            await ProjectAlias.create(
                canonical=canonical_name,
                repoId=repo_id,
                owner=owner,
                isPrivate=is_private,
                aliases=[],
                newRemote=full_name,
                isDeleted=is_archived,
                isFork=is_fork,
                deletedAt=now if is_archived else None
            )
            new_added += 1

    for p in existing_projects:
        if p.repoId and p.repoId not in fetched_map:
            if not p.isDeleted:
                logger.info(f"Repository {p.canonical} not found on GitHub, marking as deleted.")
                p.isDeleted = True
                p.deletedAt = now
                await p.save()
                updates_made += 1

    return {"status": "success", "new": new_added, "updated": updates_made, "total_fetched": len(fetched_repos)}
