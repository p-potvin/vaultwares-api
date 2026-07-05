import logging
import httpx
import os
import subprocess
from datetime import datetime
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional
from db import ProjectAlias, ProjectCommit
import asyncio
import re

EXCLUDE_PATH_REGEX = re.compile(r'(^|/|\\)(node_modules|\.venv|venv|vendor|dist|build|target|obj|bin|__pycache__|\.next|\.nuxt|\.turbo|\.cache|coverage)(/|\\|$)|\.(pyc|pyo|class|dll|exe|obj|cache|map)$', re.IGNORECASE)

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

async def sync_commits_task(token: str):
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    
    projects = await ProjectAlias.filter(isDeleted=False, isFork=False, owner__not_isnull=True, newRemote__not_isnull=True)
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        for p in projects:
            owner_repo = p.newRemote
            logger.info(f"Syncing commits for {owner_repo}")
            
            url = f"https://api.github.com/repos/{owner_repo}/commits?since=2026-03-11T00:00:00Z&per_page=100"
            commits_to_process = []
            page = 1
            while True:
                resp = await client.get(f"{url}&page={page}", headers=headers)
                if resp.status_code != 200:
                    break
                data = resp.json()
                if not data:
                    break
                for c in data:
                    commits_to_process.append(c["sha"])
                page += 1
            
            if not commits_to_process:
                continue
                
            existing_commits = await ProjectCommit.filter(hash__in=commits_to_process).values_list("hash", flat=True)
            existing_set = set(existing_commits)
            new_commits = [sha for sha in commits_to_process if sha not in existing_set]
            
            for sha in new_commits:
                detail_resp = await client.get(f"https://api.github.com/repos/{owner_repo}/commits/{sha}", headers=headers)
                if detail_resp.status_code != 200:
                    continue
                detail = detail_resp.json()
                
                raw_ins = detail.get("stats", {}).get("additions", 0)
                raw_del = detail.get("stats", {}).get("deletions", 0)
                
                clean_ins = 0
                clean_del = 0
                files_changed = 0
                
                for f in detail.get("files", []):
                    filename = f.get("filename", "")
                    files_changed += 1
                    if not EXCLUDE_PATH_REGEX.search(filename):
                        clean_ins += f.get("additions", 0)
                        clean_del += f.get("deletions", 0)
                        
                date_str = detail["commit"]["author"]["date"]
                author_name = detail["commit"]["author"]["name"]
                message = detail["commit"]["message"]
                
                try:
                    dt = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ")
                except:
                    dt = datetime.now()
                    
                await ProjectCommit.create(
                    hash=sha,
                    project=p,
                    date=dt,
                    author=author_name,
                    message=message,
                    raw_insertions=raw_ins,
                    raw_deletions=raw_del,
                    clean_insertions=clean_ins,
                    clean_deletions=clean_del,
                    files_changed=files_changed
                )


@router.get("/commits/stats")
async def get_commits_stats():
    """
    Returns commit stats required by the frontend data generator.
    """
    commits = await ProjectCommit.all().prefetch_related("project")
    samples = []
    for c in commits:
        samples.append({
            "day": c.date.strftime("%Y-%m-%d"),
            "project": c.project.canonical,
            "commit": c.hash[:7],
            "cleanChurnLines": c.clean_insertions + c.clean_deletions,
            "rawChurnLines": c.raw_insertions + c.raw_deletions,
            "files": c.files_changed
        })
    return {"data": {"commitSamples": samples}}


@router.post("/sync-github")
async def sync_github_projects(background_tasks: BackgroundTasks):
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

    background_tasks.add_task(sync_commits_task, token)
    return {"status": "success", "new": new_added, "updated": updates_made, "total_fetched": len(fetched_repos)}
