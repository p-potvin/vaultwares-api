CREATE TABLE IF NOT EXISTS input_batch_receipts (
  batch_id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL,
  source TEXT NOT NULL,
  schema_version INTEGER NOT NULL,
  host JSONB NOT NULL DEFAULT '{}'::jsonb,
  started_at TIMESTAMPTZ,
  ended_at TIMESTAMPTZ,
  received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  event_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS input_events (
  event_id TEXT PRIMARY KEY,
  batch_id TEXT NOT NULL REFERENCES input_batch_receipts(batch_id) ON DELETE CASCADE,
  session_id TEXT NOT NULL,
  source TEXT NOT NULL,
  event_type TEXT NOT NULL,
  timestamp TIMESTAMPTZ,
  bucket_start TIMESTAMPTZ,
  metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
  dimensions JSONB NOT NULL DEFAULT '{}'::jsonb,
  checksum TEXT,
  received_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_input_events_bucket_start ON input_events(bucket_start DESC);
CREATE INDEX IF NOT EXISTS idx_input_events_type ON input_events(event_type);
CREATE INDEX IF NOT EXISTS idx_input_events_session ON input_events(session_id);

CREATE TABLE IF NOT EXISTS input_minute_rollups (
  event_id TEXT PRIMARY KEY REFERENCES input_events(event_id) ON DELETE CASCADE,
  bucket_start TIMESTAMPTZ NOT NULL,
  metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
  dimensions JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS input_focus_segments (
  segment_id TEXT PRIMARY KEY,
  batch_id TEXT NOT NULL REFERENCES input_batch_receipts(batch_id) ON DELETE CASCADE,
  started_at TIMESTAMPTZ,
  ended_at TIMESTAMPTZ,
  category TEXT NOT NULL DEFAULT 'unknown',
  window_hash TEXT,
  duration_ms BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS input_pointer_hotspots (
  hotspot_id TEXT PRIMARY KEY,
  batch_id TEXT NOT NULL REFERENCES input_batch_receipts(batch_id) ON DELETE CASCADE,
  bucket_start TIMESTAMPTZ,
  x_bucket INTEGER NOT NULL,
  y_bucket INTEGER NOT NULL,
  clicks INTEGER NOT NULL DEFAULT 0,
  scroll_ticks INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS natural_paths (
  path_id TEXT PRIMARY KEY,
  event_id TEXT UNIQUE NOT NULL REFERENCES input_events(event_id) ON DELETE CASCADE,
  batch_id TEXT NOT NULL REFERENCES input_batch_receipts(batch_id) ON DELETE CASCADE,
  session_id TEXT NOT NULL,
  source TEXT NOT NULL,
  trigger TEXT NOT NULL DEFAULT 'unknown',
  started_at TIMESTAMPTZ,
  ended_at TIMESTAMPTZ,
  duration_ms BIGINT NOT NULL DEFAULT 0,
  start_context JSONB NOT NULL DEFAULT '{}'::jsonb,
  end_context JSONB NOT NULL DEFAULT '{}'::jsonb,
  mouse_path JSONB NOT NULL DEFAULT '[]'::jsonb,
  key_presses JSONB NOT NULL DEFAULT '[]'::jsonb,
  click_target JSONB NOT NULL DEFAULT '{}'::jsonb,
  stats JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_natural_paths_started_at ON natural_paths(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_natural_paths_trigger ON natural_paths(trigger);

CREATE TABLE IF NOT EXISTS input_ingest_errors (
  id BIGSERIAL PRIMARY KEY,
  batch_id TEXT,
  event_id TEXT,
  error_class TEXT NOT NULL,
  message TEXT NOT NULL,
  payload JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
