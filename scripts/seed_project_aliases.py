import asyncio
import json
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import init_db, close_db, ProjectAlias
from api.config import DB_URL

async def main():
    await init_db(DB_URL)

    with open(r"C:\Users\Administrator\Desktop\Github Repos\agent-ledger\project-aliases.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    # Note: We won't fetch repoIds here to save time, the POST /projects/sync-github will merge and assign repoIds on its first run if the canonical names or remotes match!
    # Wait, POST /projects/sync-github only matches on repoId or canonical name.
    # If the canonical name matches, it skips adding. But if repoId is missing, it won't track renames properly.
    # We should just insert them. The cron job will match on canonical name and set repoId automatically if they match!

    projects = data.get("projects", [])
    forks = data.get("forks", [])

    print(f"Seeding {len(projects)} projects and {len(forks)} forks...")

    for p in projects:
        canonical = p.get("canonical")
        if not canonical:
            continue
        
        await ProjectAlias.update_or_create(
            canonical=canonical,
            defaults={
                "aliases": p.get("aliases", []),
                "previousRemote": p.get("previousRemote"),
                "newRemote": p.get("newRemote"),
                "notes": p.get("notes"),
                "isFork": False
            }
        )
    
    for p in forks:
        canonical = p.get("canonical")
        if not canonical:
            continue
        
        await ProjectAlias.update_or_create(
            canonical=canonical,
            defaults={
                "aliases": p.get("aliases", []),
                "previousRemote": p.get("previousRemote"),
                "newRemote": p.get("newRemote"),
                "notes": p.get("notes"),
                "isFork": True
            }
        )

    print("Seed complete.")
    await close_db()

if __name__ == "__main__":
    asyncio.run(main())
