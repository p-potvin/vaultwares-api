"""Real conditions test for VaultWares API Identities Endpoints."""

import os
import sys
import sqlite3
from fastapi.testclient import TestClient

# Add vaultwares-api to sys.path
api_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if api_dir not in sys.path:
    sys.path.insert(0, api_dir)

from api.app import app

print("==================================================================")
print(" LIVE PROOF: VAULTWARES-API IDENTITIES GATEWAY ENDPOINTS          ")
print("==================================================================")

proof_db_path = os.path.join(api_dir, "data", "test_identities_gateway.db")
os.makedirs(os.path.dirname(proof_db_path), exist_ok=True)
if os.path.exists(proof_db_path):
    try: os.remove(proof_db_path)
    except Exception: pass

# Pre-populate test DB
conn = sqlite3.connect(proof_db_path)
conn.executescript("""
CREATE TABLE IF NOT EXISTS identities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    status TEXT NOT NULL DEFAULT 'soft',
    threshold REAL DEFAULT 0.50,
    sample_count INTEGER DEFAULT 0,
    created_at TEXT NOT NULL,
    validated_at TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS face_crops (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    identity_id INTEGER REFERENCES identities(id) ON DELETE CASCADE,
    model_name TEXT NOT NULL,
    image_path TEXT NOT NULL,
    rel_path TEXT NOT NULL,
    bbox TEXT,
    landmarks_5pts TEXT,
    embedding BLOB NOT NULL,
    feature_norm REAL NOT NULL DEFAULT 1.0,
    quality_score REAL DEFAULT 1.0,
    is_exemplar INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type TEXT NOT NULL,
    target_model TEXT,
    status TEXT NOT NULL,
    duration_ms INTEGER DEFAULT 0,
    images_scanned INTEGER DEFAULT 0,
    matched_count INTEGER DEFAULT 0,
    outliers_count INTEGER DEFAULT 0,
    no_face_count INTEGER DEFAULT 0,
    quarantined_count INTEGER DEFAULT 0,
    details_json TEXT,
    created_at TEXT NOT NULL
);
""")

# Insert dummy data with 512-dim float32 binary BLOB
import numpy as np
emb1 = np.random.randn(512).astype(np.float32)
emb1 = emb1 / np.linalg.norm(emb1)
emb2 = np.random.randn(512).astype(np.float32)
emb2 = emb2 / np.linalg.norm(emb2)

cur = conn.cursor()
cur.execute("INSERT INTO identities (name, status, threshold, sample_count, created_at, validated_at) VALUES ('zoemitchell', 'locked', 0.50, 6, '2026-08-28T18:00:00Z', '2026-08-28T18:00:00Z')")
cur.execute("INSERT INTO face_crops (identity_id, model_name, image_path, rel_path, embedding, feature_norm, quality_score, is_exemplar, created_at) VALUES (1, 'zoemitchell', 'F:\\amd\\gallery\\zoemitchell\\_0001.jpg', '_0001.jpg', ?, 24.5, 0.999, 1, '2026-08-28T18:00:00Z')", (emb1.tobytes(),))
cur.execute("INSERT INTO face_crops (identity_id, model_name, image_path, rel_path, embedding, feature_norm, quality_score, is_exemplar, created_at) VALUES (1, 'zoemitchell', 'F:\\amd\\gallery\\zoemitchell\\_0002.jpg', '_0002.jpg', ?, 23.8, 0.998, 0, '2026-08-28T18:00:00Z')", (emb2.tobytes(),))

cur.execute("""
INSERT INTO task_logs (task_type, target_model, status, duration_ms, images_scanned, matched_count, outliers_count, created_at)
VALUES ('clean', 'zoemitchell', 'completed', 4500, 77, 67, 7, '2026-08-28T18:05:00Z')
""")
conn.commit()
conn.close()

from api.config import GATEWAY_HEADER_NAME, GATEWAY_SHARED_SECRET

os.environ["GALLERY_DB_PATH"] = proof_db_path
client = TestClient(
    app,
    base_url="https://testserver",
    headers={
        "X-Forwarded-For": "127.0.0.1",
        "Origin": "http://localhost:5173",
        GATEWAY_HEADER_NAME: GATEWAY_SHARED_SECRET
    }
)

# 1. Summary Stats
res_sum = client.get("/api/identities/stats/summary")
assert res_sum.status_code == 200, f"Stats summary failed: {res_sum.text}"
sum_json = res_sum.json()
print(f"  - GET /api/identities/stats/summary -> Status: {res_sum.status_code}, Models: {sum_json['total_models']}, Crops: {sum_json['total_face_crops']}, Tasks: {sum_json['total_tasks_run']}")
assert sum_json["total_models"] == 1
assert sum_json["locked_models"] == 1
assert sum_json["total_face_crops"] == 2
assert sum_json["total_tasks_run"] == 1

# 2. List Identities
res_list = client.get("/api/identities")
assert res_list.status_code == 200, f"List identities failed: {res_list.text}"
list_json = res_list.json()
print(f"  - GET /api/identities -> Status: {res_list.status_code}, Count: {list_json['count']}")
assert list_json["count"] == 1
assert list_json["identities"][0]["name"] == "zoemitchell"
assert len(list_json["identities"][0]["exemplars_preview"]) == 1

# 3. 3D Embeddings Projection Endpoint
res_3d = client.get("/api/identities/telemetry/embeddings-3d")
assert res_3d.status_code == 200, f"3D embeddings failed: {res_3d.text}"
pts_json = res_3d.json()
print(f"  - GET /api/identities/telemetry/embeddings-3d -> Status: {res_3d.status_code}, Points: {pts_json['count']}")
assert pts_json["count"] == 2
assert "x" in pts_json["points"][0] and "y" in pts_json["points"][0] and "z" in pts_json["points"][0]

# 4. Task Telemetry Endpoint
res_tasks = client.get("/api/identities/telemetry/tasks")
assert res_tasks.status_code == 200, f"Task telemetry failed: {res_tasks.text}"
tasks_json = res_tasks.json()
print(f"  - GET /api/identities/telemetry/tasks -> Status: {res_tasks.status_code}, Tasks: {tasks_json['count']}")
assert tasks_json["count"] == 1

# 5. Update Identity Status
res_put = client.put("/api/identities/zoemitchell", json={"status": "locked", "threshold": 0.50, "notes": "Production verified"})
assert res_put.status_code == 200, f"Update failed: {res_put.text}"

# 6. Read-back verification directly from SQLite
conn = sqlite3.connect(proof_db_path)
cur = conn.cursor()
cur.execute("SELECT threshold, notes FROM identities WHERE name = 'zoemitchell'")
updated_row = cur.fetchone()
conn.close()
print(f"  - State Persistence Read-Back -> Threshold: {updated_row[0]}, Notes: '{updated_row[1]}' [PASS]")
assert updated_row[0] == 0.50
assert updated_row[1] == "Production verified"

if os.path.exists(proof_db_path):
    try: os.remove(proof_db_path)
    except Exception: pass

print("\n==================================================================")
print(" ALL API GATEWAY TESTS PASSED 100%!                               ")
print("==================================================================")
