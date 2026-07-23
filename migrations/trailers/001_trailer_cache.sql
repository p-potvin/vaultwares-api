-- Trailer cache — Thu, 23 Jul 2026
-- Maps a YouTube trailer (by video id) to durable hosted copies produced by the
-- server-side pipeline: yt-dlp downloads once, then fans out to the instant
-- hosts (gofile / 1fichier / pixeldrain) and submits to TorBox (slow, ~10 min,
-- durable). Replaces per-view KinoCheck + yt-dlp resolution in vault-streaming.
CREATE TABLE IF NOT EXISTS trailer_cache (
  youtube_id     TEXT PRIMARY KEY,                 -- canonical key (YouTube video id)
  tmdb_id        INTEGER,                           -- TMDB id that referenced it (optional)
  media_type     TEXT,                              -- 'movie' | 'tv' (informational)
  title          TEXT,                              -- human label for ops/debugging
  status         TEXT NOT NULL DEFAULT 'pending',   -- pending | ready | failed

  -- Per-host resolved direct URLs (nullable until each upload completes)
  pixeldrain_url TEXT,
  gofile_url     TEXT,
  onefichier_url TEXT,
  torbox_url     TEXT,

  primary_url    TEXT,                              -- host the client should prefer to stream
  duration_sec   INTEGER,
  filesize       BIGINT,
  error          TEXT,                              -- last failure detail when status='failed'

  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  ready_at       TIMESTAMPTZ                        -- first time an instant host became playable
);

CREATE INDEX IF NOT EXISTS idx_trailer_cache_status ON trailer_cache(status);
CREATE INDEX IF NOT EXISTS idx_trailer_cache_tmdb   ON trailer_cache(tmdb_id);
