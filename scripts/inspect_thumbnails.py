import asyncio
import asyncpg

async def main():
    dsn = "postgres://postgres:USIpIIfFC-edPvJqp5nxFsLySo8JpDp0@127.0.0.1:5433/promking"
    conn = await asyncpg.connect(dsn)
    try:
        # Check patterns of non-https thumbnail URLs
        rows = await conn.fetch("""
            SELECT id, source, thumbnail_url
            FROM videos
            WHERE thumbnail_url IS NOT NULL
              AND thumbnail_url NOT LIKE 'https://%'
              AND thumbnail_url != ''
            LIMIT 30;
        """)
        print(f"Sample of {len(rows)} non-https thumbnails:")
        for r in rows:
            print(f"[{r['source']}] id={r['id']}: {repr(r['thumbnail_url'])}")

        counts = await conn.fetch("""
            SELECT 
                source,
                CASE 
                    WHEN thumbnail_url LIKE 'http://%' THEN 'http://'
                    WHEN thumbnail_url LIKE '//%' THEN '//'
                    WHEN thumbnail_url LIKE '/%' THEN 'relative-path'
                    ELSE 'other'
                END as pattern,
                COUNT(*) as count
            FROM videos
            WHERE thumbnail_url IS NOT NULL
              AND thumbnail_url NOT LIKE 'https://%'
              AND thumbnail_url != ''
            GROUP BY source, pattern
            ORDER BY count DESC;
        """)
        print("\nSummary by pattern & source:")
        for c in counts:
            print(f"Source: {c['source']}, Pattern: {c['pattern']}, Count: {c['count']}")

        # Also count missing/empty
        missing = await conn.fetchval("SELECT count(*) FROM videos WHERE thumbnail_url IS NULL OR thumbnail_url = '';")
        total = await conn.fetchval("SELECT count(*) FROM videos;")
        print(f"\nTotal videos: {total}, Missing/empty thumbnail: {missing}")

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
