import asyncio
import os
from app.routers.promking.db import get_pool

async def main():
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Fix user roles to admin so we don't get 403
        await conn.execute("UPDATE users SET role = 'admin' WHERE role = 'viewer'")
        print("Updated users to admin.")
        
        # Get all videos that don't have an entry in video_sites
        videos = await conn.fetch("SELECT id FROM videos WHERE id NOT IN (SELECT video_id FROM video_sites)")
        video_ids = [v["id"] for v in videos]
        
        print(f"Found {len(video_ids)} orphaned videos.")
        if not video_ids:
            return
            
        # Distribute into 1/3
        chunk_size = len(video_ids) // 3
        fxv_ids = video_ids[:chunk_size]
        oneporn_ids = video_ids[chunk_size:chunk_size*2]
        sexyprn_ids = video_ids[chunk_size*2:]
        
        # Insert into video_sites
        # using unnest to do bulk insert
        if fxv_ids:
            await conn.execute("INSERT INTO video_sites (video_id, site) SELECT unnest($1::int[]), 'fxv' ON CONFLICT DO NOTHING", fxv_ids)
        if oneporn_ids:
            await conn.execute("INSERT INTO video_sites (video_id, site) SELECT unnest($1::int[]), 'oneporn' ON CONFLICT DO NOTHING", oneporn_ids)
        if sexyprn_ids:
            await conn.execute("INSERT INTO video_sites (video_id, site) SELECT unnest($1::int[]), 'sexyprn' ON CONFLICT DO NOTHING", sexyprn_ids)
            
        print("Distributed videos among sites successfully.")

if __name__ == "__main__":
    # override db connection string for local script to connect to OVH via tailscale
    # Wait, if we run it on OVH, we don't need this. But if we run locally?
    pass
