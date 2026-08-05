-- AI assistant session telemetry.
-- Fed by `vw collect-ai-history` -> D:\AiHistory\spool -> drain-ai-sessions.ps1.
-- One row per conversation across every assistant on every host.

CREATE TABLE IF NOT EXISTS ai_session_batch_receipts (
  batch_id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  schema_version INTEGER NOT NULL,
  host TEXT NOT NULL,
  batch_index INTEGER NOT NULL DEFAULT 0,
  collected_at TIMESTAMPTZ,
  received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  session_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS ai_sessions (
  -- (host, tool, session_id) is the natural key: session ids are only unique
  -- within a tool, and the same tool runs on several machines.
  host TEXT NOT NULL,
  tool TEXT NOT NULL,
  session_id TEXT NOT NULL,
  batch_id TEXT REFERENCES ai_session_batch_receipts(batch_id) ON DELETE SET NULL,
  title TEXT,
  project TEXT,
  cwd TEXT,
  model TEXT,
  started_at TIMESTAMPTZ,
  last_activity_at TIMESTAMPTZ,
  message_count INTEGER,
  user_message_count INTEGER,
  tokens_used BIGINT,
  input_tokens BIGINT,
  output_tokens BIGINT,
  cached_input_tokens BIGINT,
  reasoning_tokens BIGINT,
  archived BOOLEAN,
  git_branch TEXT,
  source_path TEXT,
  size_bytes BIGINT,
  parser TEXT NOT NULL DEFAULT 'full',
  extra JSONB NOT NULL DEFAULT '{}'::jsonb,
  first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (host, tool, session_id)
);

CREATE INDEX IF NOT EXISTS idx_ai_sessions_last_activity ON ai_sessions(last_activity_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_sessions_tool ON ai_sessions(tool);
CREATE INDEX IF NOT EXISTS idx_ai_sessions_host ON ai_sessions(host);
CREATE INDEX IF NOT EXISTS idx_ai_sessions_project ON ai_sessions(lower(project));
CREATE INDEX IF NOT EXISTS idx_ai_sessions_model ON ai_sessions(model);
CREATE INDEX IF NOT EXISTS idx_ai_sessions_started ON ai_sessions(started_at DESC);

-- Trigram-ish title search without requiring pg_trgm: plain prefix/ILIKE is
-- enough at this row count, but keep a lowered expression index for it.
CREATE INDEX IF NOT EXISTS idx_ai_sessions_title_lower ON ai_sessions(lower(title));
