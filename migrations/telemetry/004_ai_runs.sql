-- Model-run telemetry: one row per model invocation, every provider.
-- Fed by vaultwares_adk.telemetry -> run-spool -> drain-ai-runs.ps1.
--
-- Distinct from ai_sessions on purpose: a session is a conversation, a run is a
-- single invocation. Runs are append-only events with their own id, so ingest
-- is INSERT ... ON CONFLICT DO NOTHING rather than the session upsert.

CREATE TABLE IF NOT EXISTS ai_run_batch_receipts (
  batch_id TEXT PRIMARY KEY,
  source TEXT NOT NULL,
  schema_version INTEGER NOT NULL,
  host TEXT NOT NULL,
  batch_index INTEGER NOT NULL DEFAULT 0,
  collected_at TIMESTAMPTZ,
  received_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  run_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS ai_runs (
  run_id TEXT PRIMARY KEY,
  parent_run_id TEXT,
  batch_id TEXT REFERENCES ai_run_batch_receipts(batch_id) ON DELETE SET NULL,

  -- identity
  provider TEXT NOT NULL,
  runtime TEXT NOT NULL,
  model TEXT NOT NULL,
  model_revision TEXT,
  quantization TEXT,
  task TEXT,

  -- attribution
  host TEXT,
  project TEXT,
  service TEXT,
  session_id TEXT,
  caller TEXT,
  environment TEXT,

  -- timing
  queued_at TIMESTAMPTZ,
  started_at TIMESTAMPTZ,
  first_token_at TIMESTAMPTZ,
  ended_at TIMESTAMPTZ,
  queue_ms DOUBLE PRECISION,
  ttft_ms DOUBLE PRECISION,
  duration_ms DOUBLE PRECISION,
  tokens_per_second DOUBLE PRECISION,

  -- tokens
  input_tokens BIGINT,
  output_tokens BIGINT,
  cached_input_tokens BIGINT,
  reasoning_tokens BIGINT,
  total_tokens BIGINT,

  -- request parameters
  temperature DOUBLE PRECISION,
  top_p DOUBLE PRECISION,
  max_tokens INTEGER,
  seed BIGINT,
  stream BOOLEAN,
  batch_size INTEGER,
  context_length INTEGER,

  -- outcome
  status TEXT NOT NULL DEFAULT 'ok',
  finish_reason TEXT,
  error_class TEXT,
  error_message TEXT,
  http_status INTEGER,
  retries INTEGER NOT NULL DEFAULT 0,

  -- provider round-trip. provider_ms is the upstream's own time;
  -- duration_ms - provider_ms is our gateway overhead.
  request_id TEXT,
  served_model TEXT,
  upstream_provider TEXT,
  provider_ms DOUBLE PRECISION,
  backend TEXT,
  role TEXT,
  load_ms DOUBLE PRECISION,

  -- cost. priced_exactly separates a real figure from a worst-case guess;
  -- cost_state separates a settled cost from one the reconciliation pass will
  -- still correct (embeddings bill by time, so they land provisional at 0).
  cost_usd DOUBLE PRECISION,
  credits_used DOUBLE PRECISION,
  billing_source TEXT,
  budget_remaining DOUBLE PRECISION,
  is_free BOOLEAN,
  priced_exactly BOOLEAN,
  cost_state TEXT NOT NULL DEFAULT 'settled',

  -- hardware
  device TEXT,
  gpu_name TEXT,
  gpu_index INTEGER,
  gpu_util_pct DOUBLE PRECISION,
  gpu_temp_c DOUBLE PRECISION,
  gpu_power_w DOUBLE PRECISION,
  vram_used_mb DOUBLE PRECISION,
  vram_peak_mb DOUBLE PRECISION,
  vram_total_mb DOUBLE PRECISION,
  cpu_pct DOUBLE PRECISION,
  rss_mb DOUBLE PRECISION,

  -- payload shape (never content)
  prompt_chars INTEGER,
  prompt_hash TEXT,
  completion_chars INTEGER,
  image_count INTEGER,
  audio_seconds DOUBLE PRECISION,
  video_frames INTEGER,
  output_bytes BIGINT,

  -- diffusion / media
  steps INTEGER,
  sampler TEXT,
  scheduler TEXT,
  cfg_scale DOUBLE PRECISION,
  width INTEGER,
  height INTEGER,
  lora_count INTEGER,

  tags TEXT[] NOT NULL DEFAULT '{}',
  extra JSONB NOT NULL DEFAULT '{}'::jsonb,
  received_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Almost every widget filters on a time window first, so the time indexes carry
-- the load. BRIN is the right shape here: runs arrive in rough time order and
-- the table is append-only, so it stays tiny next to a btree over the same data.
CREATE INDEX IF NOT EXISTS idx_ai_runs_started_brin ON ai_runs USING BRIN (started_at);
CREATE INDEX IF NOT EXISTS idx_ai_runs_started ON ai_runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_runs_provider ON ai_runs(provider);
CREATE INDEX IF NOT EXISTS idx_ai_runs_runtime ON ai_runs(runtime);
CREATE INDEX IF NOT EXISTS idx_ai_runs_model ON ai_runs(model);
CREATE INDEX IF NOT EXISTS idx_ai_runs_project ON ai_runs(lower(project));
CREATE INDEX IF NOT EXISTS idx_ai_runs_host ON ai_runs(host);
CREATE INDEX IF NOT EXISTS idx_ai_runs_task ON ai_runs(task);

-- Failure widgets only ever look at the non-ok slice, which is a small minority
-- of rows; a partial index keeps that lookup off the main table.
CREATE INDEX IF NOT EXISTS idx_ai_runs_failures
  ON ai_runs(started_at DESC, error_class)
  WHERE status <> 'ok';

CREATE INDEX IF NOT EXISTS idx_ai_runs_session ON ai_runs(session_id) WHERE session_id IS NOT NULL;

-- The reconciliation pass reads only the provisional slice; it is a small
-- minority of rows, so a partial index keeps that scan off the main table.
CREATE INDEX IF NOT EXISTS idx_ai_runs_provisional
  ON ai_runs(started_at) WHERE cost_state <> 'settled';

-- HF's X-Request-ID traces a row back to them, and gives the drain a second
-- dedupe key when a spool file is replayed.
CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_runs_request_id
  ON ai_runs(request_id) WHERE request_id IS NOT NULL;
