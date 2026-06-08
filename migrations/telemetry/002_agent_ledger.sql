CREATE TABLE IF NOT EXISTS agent_ledger_events (
  id TEXT PRIMARY KEY,
  content_hash TEXT,
  created_at TIMESTAMPTZ,
  created_at_local TEXT,
  timezone TEXT,
  project TEXT NOT NULL DEFAULT 'General Tasks',
  kind TEXT NOT NULL DEFAULT 'general',
  actor TEXT,
  summary TEXT NOT NULL DEFAULT '',
  commands JSONB NOT NULL DEFAULT '[]'::jsonb,
  files JSONB NOT NULL DEFAULT '[]'::jsonb,
  runtime JSONB NOT NULL DEFAULT '{}'::jsonb,
  telemetry JSONB NOT NULL DEFAULT '{}'::jsonb,
  git JSONB,
  plan_path TEXT,
  workspace_root TEXT,
  cwd TEXT,
  source_path TEXT,
  raw JSONB NOT NULL,
  ingested_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_ledger_events_content_hash
  ON agent_ledger_events(content_hash)
  WHERE content_hash IS NOT NULL AND content_hash <> '';

CREATE INDEX IF NOT EXISTS idx_agent_ledger_events_created_at
  ON agent_ledger_events(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_agent_ledger_events_project
  ON agent_ledger_events(project);

CREATE INDEX IF NOT EXISTS idx_agent_ledger_events_kind
  ON agent_ledger_events(kind);

CREATE INDEX IF NOT EXISTS idx_agent_ledger_events_summary_search
  ON agent_ledger_events USING gin (
    to_tsvector('simple', coalesce(project, '') || ' ' || coalesce(kind, '') || ' ' || coalesce(summary, ''))
  );
