"""FastAPI router for Model Identities, ArcFace Multi-Vector Crops, 3D Projections, and Task Telemetry."""

import json
import os
import sqlite3
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/identities", tags=["identities"])

# Path to SQLite gallery DB (can be set via env var GALLERY_DB_PATH)
def get_gallery_db_path() -> str:
    env_path = os.environ.get("GALLERY_DB_PATH")
    if env_path:
        return os.path.abspath(env_path)
    
    # Check default paths based on OS
    if os.name == "nt":
        candidates = [
            r"F:\amd\gallery\gallery.db",
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "gallery.db"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "ColONEL-KFC", "gallery.db"),
        ]
    else:
        candidates = [
            "/var/lib/vaultwares/gallery.db",
            "/opt/vaultwares-api/data/gallery.db",
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "gallery.db"),
            os.path.join(os.path.expanduser("~"), "gallery.db")
        ]

    for c in candidates:
        if os.path.isfile(c):
            return os.path.abspath(c)

    # Fallback to local data/gallery.db
    default_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
    return os.path.abspath(os.path.join(default_dir, "gallery.db"))


def get_db_conn():
    db_path = get_gallery_db_path()
    parent_dir = os.path.dirname(db_path)
    if parent_dir and not os.path.exists(parent_dir):
        os.makedirs(parent_dir, exist_ok=True)

    conn = sqlite3.connect(db_path, timeout=15.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")

    # Ensure tables exist
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
    conn.commit()
    return conn


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic Request Models
# ─────────────────────────────────────────────────────────────────────────────
class IdentityCreateRequest(BaseModel):
    name: str = Field(..., description="Model name identifier (e.g. 'zoemitchell')")
    status: str = Field("soft", description="Identity status: 'soft', 'locked', or 'invalid'")
    threshold: float = Field(0.50, description="ArcFace matching threshold")
    sample_count: int = Field(0, description="Number of exemplar samples")
    notes: Optional[str] = None


class IdentityUpdateRequest(BaseModel):
    status: Optional[str] = None
    threshold: Optional[float] = None
    sample_count: Optional[int] = None
    notes: Optional[str] = None


class TaskLogCreateRequest(BaseModel):
    task_type: str = Field(..., description="Type of task: clean, recalculate, create, scan_and_add, sweep")
    target_model: Optional[str] = None
    status: str = Field("completed", description="Status: completed or failed")
    duration_ms: int = Field(0, description="Duration in milliseconds")
    images_scanned: int = 0
    matched_count: int = 0
    outliers_count: int = 0
    no_face_count: int = 0
    quarantined_count: int = 0
    details: Optional[Dict[str, Any]] = None


# ─────────────────────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/stats/summary")
async def get_identities_summary():
    """Returns top-level KPIs and summary statistics for the Identities dashboard."""
    try:
        with get_db_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT 
                    COUNT(*) as total_models,
                    SUM(CASE WHEN status = 'locked' THEN 1 ELSE 0 END) as locked_models,
                    SUM(CASE WHEN status = 'soft' THEN 1 ELSE 0 END) as soft_models,
                    SUM(CASE WHEN status = 'invalid' THEN 1 ELSE 0 END) as invalid_models
                FROM identities
            """)
            i_row = dict(cur.fetchone() or {})

            cur.execute("""
                SELECT 
                    COUNT(*) as total_crops,
                    SUM(is_exemplar) as exemplars,
                    AVG(quality_score) as avg_quality,
                    AVG(feature_norm) as avg_norm
                FROM face_crops
            """)
            c_row = dict(cur.fetchone() or {})

            cur.execute("""
                SELECT 
                    COUNT(*) as total_tasks,
                    SUM(images_scanned) as total_scanned,
                    SUM(outliers_count) as total_outliers,
                    AVG(duration_ms) as avg_duration_ms
                FROM task_logs
            """)
            t_row = dict(cur.fetchone() or {})

            return {
                "total_models": i_row.get("total_models") or 0,
                "locked_models": i_row.get("locked_models") or 0,
                "soft_models": i_row.get("soft_models") or 0,
                "invalid_models": i_row.get("invalid_models") or 0,
                "total_face_crops": c_row.get("total_crops") or 0,
                "exemplars_count": c_row.get("exemplars") or 0,
                "avg_quality_score": round(c_row.get("avg_quality") or 0.0, 3),
                "avg_feature_norm": round(c_row.get("avg_norm") or 0.0, 2),
                "total_tasks_run": t_row.get("total_tasks") or 0,
                "total_images_processed": t_row.get("total_scanned") or 0,
                "total_outliers_isolated": t_row.get("total_outliers") or 0,
                "avg_task_duration_ms": round(t_row.get("avg_duration_ms") or 0.0, 1)
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")


@router.get("")
async def list_identities(
    status_filter: Optional[str] = Query(None, alias="status"),
    search: Optional[str] = None
):
    """List all model identities with crop counts and preview avatars."""
    try:
        with get_db_conn() as conn:
            cur = conn.cursor()
            query = """
                SELECT 
                    i.id, i.name, i.status, i.threshold, i.sample_count,
                    i.created_at, i.validated_at, i.notes,
                    COUNT(c.id) as crop_count,
                    SUM(CASE WHEN c.is_exemplar = 1 THEN 1 ELSE 0 END) as exemplar_count
                FROM identities i
                LEFT JOIN face_crops c ON i.id = c.identity_id
                WHERE 1=1
            """
            params = []
            if status_filter:
                query += " AND i.status = ?"
                params.append(status_filter)
            if search:
                query += " AND i.name LIKE ?"
                params.append(f"%{search.strip().lower()}%")
            
            query += " GROUP BY i.id ORDER BY i.status ASC, i.name ASC"
            cur.execute(query, params)
            rows = [dict(r) for r in cur.fetchall()]

            # Fetch exemplar previews for each model
            for row in rows:
                cur.execute("""
                    SELECT rel_path, quality_score, feature_norm
                    FROM face_crops
                    WHERE identity_id = ? AND is_exemplar = 1
                    LIMIT 3
                """, (row["id"],))
                row["exemplars_preview"] = [dict(cr) for cr in cur.fetchall()]

            return {"identities": rows, "count": len(rows)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")


@router.get("/{name}")
async def get_identity(name: str):
    """Retrieve details for a single model identity and its face crops."""
    try:
        with get_db_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM identities WHERE name = ?", (name,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"Identity '{name}' not found")
            
            identity = dict(row)
            cur.execute("""
                SELECT id, model_name, image_path, rel_path, bbox, landmarks_5pts,
                       feature_norm, quality_score, is_exemplar, created_at
                FROM face_crops
                WHERE identity_id = ?
                ORDER BY is_exemplar DESC, id ASC
            """, (identity["id"],))
            identity["crops"] = [dict(cr) for cr in cur.fetchall()]
            return identity
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_identity(req: IdentityCreateRequest):
    """Create or register a model identity."""
    try:
        with get_db_conn() as conn:
            cur = conn.cursor()
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            val_at = now if req.status == "locked" else None
            cur.execute("""
                INSERT INTO identities (name, status, threshold, sample_count, created_at, validated_at, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (req.name.strip().lower(), req.status, req.threshold, req.sample_count, now, val_at, req.notes))
            conn.commit()
            return {"id": cur.lastrowid, "name": req.name, "status": req.status}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail=f"Identity '{req.name}' already exists")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")


@router.put("/{name}")
async def update_identity(name: str, req: IdentityUpdateRequest):
    """Update identity properties (status, threshold, notes)."""
    try:
        with get_db_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM identities WHERE name = ?", (name,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail=f"Identity '{name}' not found")
            
            updates = []
            params = []
            if req.status is not None:
                updates.append("status = ?")
                params.append(req.status)
                if req.status == "locked" and not row["validated_at"]:
                    from datetime import datetime, timezone
                    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                    updates.append("validated_at = ?")
                    params.append(now)
            if req.threshold is not None:
                updates.append("threshold = ?")
                params.append(req.threshold)
            if req.sample_count is not None:
                updates.append("sample_count = ?")
                params.append(req.sample_count)
            if req.notes is not None:
                updates.append("notes = ?")
                params.append(req.notes)

            if updates:
                params.append(name)
                cur.execute(f"UPDATE identities SET {', '.join(updates)} WHERE name = ?", params)
                conn.commit()

            return {"status": "updated", "name": name}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")


@router.delete("/{name}")
async def delete_identity(name: str):
    """Delete an identity and cascade delete its face crops."""
    try:
        with get_db_conn() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM identities WHERE name = ?", (name,))
            conn.commit()
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail=f"Identity '{name}' not found")
            return {"status": "deleted", "name": name}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# 3D Dimensionality Reduced Embeddings Projection
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/telemetry/embeddings-3d")
async def get_3d_embeddings_projection():
    """Returns 3D (x, y, z) PCA projected coordinates for face crops across models for 3D point cloud rendering."""
    try:
        import numpy as np
        with get_db_conn() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT c.id, c.model_name, c.rel_path, c.feature_norm, c.quality_score, c.is_exemplar, c.embedding, i.status as model_status
                FROM face_crops c
                JOIN identities i ON c.identity_id = i.id
                ORDER BY c.model_name ASC, c.id ASC
            """)
            rows = cur.fetchall()
            if not rows:
                return {"points": [], "count": 0}

            embs = []
            metadata = []
            for r in rows:
                blob = r["embedding"]
                emb_vec = np.frombuffer(blob, dtype=np.float32)
                embs.append(emb_vec)
                metadata.append({
                    "id": r["id"],
                    "model_name": r["model_name"],
                    "model_status": r["model_status"],
                    "rel_path": r["rel_path"],
                    "feature_norm": float(r["feature_norm"]),
                    "quality_score": float(r["quality_score"]),
                    "is_exemplar": bool(r["is_exemplar"])
                })

            matrix = np.vstack(embs)
            n_samples = matrix.shape[0]

            if n_samples < 3:
                coords_3d = np.random.uniform(-0.5, 0.5, (n_samples, 3)).astype(np.float32)
            else:
                mean_vec = np.mean(matrix, axis=0)
                centered = matrix - mean_vec
                u, s, vt = np.linalg.svd(centered, full_matrices=False)
                coords_3d = np.dot(centered, vt[:3].T)
                max_val = np.max(np.abs(coords_3d))
                if max_val > 1e-6:
                    coords_3d = coords_3d / max_val

            points = []
            for meta, pt in zip(metadata, coords_3d):
                points.append({
                    **meta,
                    "x": round(float(pt[0]), 4),
                    "y": round(float(pt[1]), 4),
                    "z": round(float(pt[2]), 4)
                })

            return {"points": points, "count": len(points)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error projecting 3D embeddings: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Task Telemetry Logging
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/telemetry/tasks")
async def get_task_telemetry(limit: int = Query(50, ge=1, le=200)):
    """Returns recent task execution logs and metrics."""
    try:
        with get_db_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM task_logs ORDER BY id DESC LIMIT ?", (limit,))
            rows = cur.fetchall()
            logs = []
            for r in rows:
                d = dict(r)
                if d.get("details_json"):
                    try: d["details"] = json.loads(d["details_json"])
                    except Exception: d["details"] = None
                logs.append(d)
            return {"tasks": logs, "count": len(logs)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")


@router.post("/telemetry/tasks", status_code=status.HTTP_201_CREATED)
async def record_task_log(req: TaskLogCreateRequest):
    """Records a task execution log into the SQLite telemetry store."""
    try:
        with get_db_conn() as conn:
            cur = conn.cursor()
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            details_str = json.dumps(req.details) if req.details else None
            cur.execute("""
                INSERT INTO task_logs (
                    task_type, target_model, status, duration_ms, images_scanned,
                    matched_count, outliers_count, no_face_count, quarantined_count,
                    details_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                req.task_type, req.target_model, req.status, req.duration_ms,
                req.images_scanned, req.matched_count, req.outliers_count,
                req.no_face_count, req.quarantined_count, details_str, now
            ))
            conn.commit()
            return {"status": "recorded", "id": cur.lastrowid}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
