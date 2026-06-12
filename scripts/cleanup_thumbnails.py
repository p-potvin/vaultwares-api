import asyncio
import os
import asyncpg

async def main():
    dsn = os.environ.get("PROMKING_DATABASE_URL", "postgres://postgres:postgres@localhost:5432/promking")
    print(f"Connecting to database...")
    conn = await asyncpg.connect(dsn)
    
    # Check count of bad thumbnails
    bad_count = await conn.fetchval(
        "SELECT count(*) FROM videos WHERE thumbnail_url LIKE '%spinner%' OR thumbnail_url LIKE '%placeholder%'"
    )
    print(f"Number of videos with bad/spinner/placeholder thumbnail URL: {bad_count}")
    
    if bad_count > 0:
        print("Cleaning up database by setting these thumbnail URLs to NULL...")
        updated = await conn.execute(
            "UPDATE videos SET thumbnail_url = NULL WHERE thumbnail_url LIKE '%spinner%' OR thumbnail_url LIKE '%placeholder%'"
        )
        print(f"Result: {updated}")
    else:
        print("No bad thumbnails found. Database is clean!")
        
    await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
