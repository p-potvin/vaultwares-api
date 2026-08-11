-- Hourly model-run rollups.
--
-- The durable grain. Per-run rows in ai_runs are a short debugging window and
-- can be pruned; these survive, so every long-window KPI reads from here rather
-- than scanning raw invocations.
--
-- Rows are IDEMPOTENT OVERWRITES, not increments. A host only ships an hour
-- once it has closed, so the value it sends is final for that host; a replayed
-- spool file must overwrite rather than add, or an at-least-once drain would
-- double-count. Cross-host totals come from summing rows, not from merging
-- them in place.

CREATE TABLE IF NOT EXISTS ai_run_rollups (
  hour TIMESTAMPTZ NOT NULL,

  -- The dimension tuple. Nothing unbounded here: keeping run_id or request_id
  -- out is what makes this a rollup rather than a slower copy of ai_runs.
  provider TEXT NOT NULL,
  runtime TEXT NOT NULL,
  model TEXT NOT NULL,
  task TEXT NOT NULL DEFAULT 'unknown',
  project TEXT NOT NULL DEFAULT 'unknown',
  host TEXT NOT NULL DEFAULT 'unknown',
  status TEXT NOT NULL DEFAULT 'ok',

  runs BIGINT NOT NULL DEFAULT 0,
  failures BIGINT NOT NULL DEFAULT 0,
  retries BIGINT NOT NULL DEFAULT 0,
  free_runs BIGINT NOT NULL DEFAULT 0,

  input_tokens BIGINT NOT NULL DEFAULT 0,
  output_tokens BIGINT NOT NULL DEFAULT 0,
  cached_input_tokens BIGINT NOT NULL DEFAULT 0,
  reasoning_tokens BIGINT NOT NULL DEFAULT 0,
  total_tokens BIGINT NOT NULL DEFAULT 0,

  -- Settled and provisional spend stay apart: a provisional figure is a
  -- placeholder the reconciliation pass will replace, and folding it into the
  -- settled total would make spend look real before it is.
  cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
  cost_usd_provisional DOUBLE PRECISION NOT NULL DEFAULT 0,

  -- Sums carry their own counts so an average excludes runs that never
  -- reported the field, instead of counting them as zero.
  duration_ms_sum DOUBLE PRECISION NOT NULL DEFAULT 0,
  duration_ms_min DOUBLE PRECISION,
  duration_ms_max DOUBLE PRECISION,
  ttft_ms_sum DOUBLE PRECISION NOT NULL DEFAULT 0,
  ttft_ms_count BIGINT NOT NULL DEFAULT 0,
  ttft_ms_max DOUBLE PRECISION,
  queue_ms_sum DOUBLE PRECISION NOT NULL DEFAULT 0,
  queue_ms_count BIGINT NOT NULL DEFAULT 0,
  tokens_per_second_sum DOUBLE PRECISION NOT NULL DEFAULT 0,
  tokens_per_second_count BIGINT NOT NULL DEFAULT 0,

  vram_peak_mb_max DOUBLE PRECISION,
  gpu_util_pct_sum DOUBLE PRECISION NOT NULL DEFAULT 0,
  gpu_util_pct_count BIGINT NOT NULL DEFAULT 0,

  -- Fixed-edge duration histogram. Percentiles are not mergeable — you cannot
  -- average a p95 — but these bins add elementwise across hosts and across two
  -- sends of the same hour, and still answer p50/p95 by interpolation. Edges
  -- match vaultwares_adk.telemetry.rollup.DURATION_EDGES_MS exactly; they
  -- change together or not at all.
  duration_hist BIGINT[] NOT NULL DEFAULT '{}',

  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

  PRIMARY KEY (hour, host, provider, runtime, model, task, project, status)
);

CREATE INDEX IF NOT EXISTS idx_ai_run_rollups_hour ON ai_run_rollups(hour DESC);
CREATE INDEX IF NOT EXISTS idx_ai_run_rollups_model ON ai_run_rollups(model);
CREATE INDEX IF NOT EXISTS idx_ai_run_rollups_provider ON ai_run_rollups(provider);
CREATE INDEX IF NOT EXISTS idx_ai_run_rollups_project ON ai_run_rollups(lower(project));

-- The reconciliation pass looks only at hours that still hold provisional
-- spend, which is a small minority.
CREATE INDEX IF NOT EXISTS idx_ai_run_rollups_provisional
  ON ai_run_rollups(hour) WHERE cost_usd_provisional > 0;
