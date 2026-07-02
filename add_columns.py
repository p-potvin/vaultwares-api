import asyncio
import os
import asyncpg
from dotenv import load_dotenv

load_dotenv()

async def main():
    dsn = os.environ.get("PROMKING_DATABASE_URL")
    if dsn and dsn.startswith("postgresql://"):
        dsn = "postgres://" + dsn[len("postgresql://"):]
    if not dsn:
        raise RuntimeError("PROMKING_DATABASE_URL is required")

    print("Connecting to configured Prom-King database")
    conn = await asyncpg.connect(dsn)
    
    try:
        # Add columns if they don't exist
        columns = [
            "redgifs_url TEXT",
            "google_drive_url TEXT",
            "linkvertise_url_fxv TEXT",
            "linkvertise_url_pkt TEXT",
            "fileboom_url TEXT"
        ]
        for col in columns:
            col_name = col.split()[0]
            try:
                await conn.execute(f"ALTER TABLE link_sharing ADD COLUMN {col}")
                print(f"Added column {col_name}")
            except asyncpg.exceptions.DuplicateColumnError:
                print(f"Column {col_name} already exists")
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(main())
