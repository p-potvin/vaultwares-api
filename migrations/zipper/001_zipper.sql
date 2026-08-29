-- Zipper: jobs, per-domain harvest memory, download history, provider quotas.
--
-- Applied idempotently at runtime by app/routers/zipper/db.py on first pool
-- use, matching the telemetry router's convention. Safe to re-run.
--
-- Everything the zipper knows lives here so any machine — the workstation
-- worker, the OVH media stack, a second browser — sees the same state through
-- the API. Two things specifically only work when centralised:
--   * site profiles, because a profile learned on one machine should make
--     every other machine's first visit to that domain cheap;
--   * provider quotas, because per-provider limits are only correct if every
--     grabber counts against one ledger. Two local counters each think they
--     are at half quota.

CREATE SCHEMA IF NOT EXISTS zipper;

-- ---------------------------------------------------------------- jobs -----
-- A unit of work handed to a worker. Workers claim rather than being pushed
-- to, so the workstation can be off and the queue simply waits.

CREATE TABLE IF NOT EXISTS zipper.jobs (
    id              TEXT PRIMARY KEY,
    kind            TEXT NOT NULL,              -- batch | stream | handoff
    status          TEXT NOT NULL DEFAULT 'queued',
                                                -- queued|claimed|running|completed|failed|aborted
    page_url        TEXT,
    page_domain     TEXT,                       -- profile key: the PAGE's domain
    title           TEXT,
    route           TEXT,                       -- browser|server|debrid|prowlarr|qbit
    links           JSONB NOT NULL DEFAULT '[]'::jsonb,
    link_kinds      JSONB NOT NULL DEFAULT '{}'::jsonb,
    headers         JSONB NOT NULL DEFAULT '{}'::jsonb,
    options         JSONB NOT NULL DEFAULT '{}'::jsonb,

    total_links     INTEGER NOT NULL DEFAULT 0,
    processed_links INTEGER NOT NULL DEFAULT 0,
    bytes_total     BIGINT  NOT NULL DEFAULT 0,
    bytes_done      BIGINT  NOT NULL DEFAULT 0,
    progress        REAL    NOT NULL DEFAULT 0,
    speed           BIGINT,
    eta             INTEGER,

    archives        JSONB NOT NULL DEFAULT '[]'::jsonb,
    save_dir        TEXT,
    -- Which rclone remotes actually took the files. Empty means they are still
    -- on the worker's own disk, which is a normal outcome and not a failure --
    -- but it is a different one, and a bare "complete" could not tell them
    -- apart. This is the first thing anyone asks when going to look for a file.
    rclone_remotes  JSONB NOT NULL DEFAULT '[]'::jsonb,
    error           TEXT,

    -- Claim bookkeeping. claimed_at lets a stalled claim be reaped rather than
    -- stranding the job forever when a worker dies mid-flight.
    claimed_by      TEXT,
    claimed_at      TIMESTAMPTZ,
    heartbeat_at    TIMESTAMPTZ,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS zipper_jobs_status_idx  ON zipper.jobs (status, created_at DESC);
CREATE INDEX IF NOT EXISTS zipper_jobs_domain_idx  ON zipper.jobs (page_domain);
CREATE INDEX IF NOT EXISTS zipper_jobs_claim_idx   ON zipper.jobs (status, kind, created_at)
    WHERE status = 'queued';

-- ------------------------------------------------------------- history -----
-- One row per file we actually took. This is both the Insights source and the
-- training signal the site profiles learn from — accepted vs rejected is the
-- only label we get for free, and it is a reliable one.

CREATE TABLE IF NOT EXISTS zipper.history (
    id          BIGSERIAL PRIMARY KEY,
    ts          TIMESTAMPTZ NOT NULL DEFAULT now(),
    job_id      TEXT REFERENCES zipper.jobs(id) ON DELETE SET NULL,

    domain      TEXT NOT NULL,                  -- the PAGE's registrable domain
    asset_host  TEXT,                           -- who served the bytes
    page_url    TEXT,
    page_title  TEXT,
    url         TEXT NOT NULL,
    url_key     TEXT NOT NULL,                  -- dedupKey(url); what "already got" matches on

    kind        TEXT,
    mime        TEXT,
    bytes       BIGINT,
    width       INTEGER,
    height      INTEGER,
    origin      TEXT,                           -- dom|network|carousel|meta|text
    score       INTEGER,

    saved_as    TEXT,                           -- the name on disk
    route       TEXT,
    outcome     TEXT NOT NULL DEFAULT 'ok',     -- ok|failed|skipped
    accepted    BOOLEAN NOT NULL DEFAULT TRUE,  -- FALSE = deselected/rejected
    duration_ms INTEGER,
    speed       BIGINT
);

CREATE INDEX IF NOT EXISTS zipper_history_domain_idx ON zipper.history (domain, ts DESC);
CREATE INDEX IF NOT EXISTS zipper_history_ts_idx     ON zipper.history (ts DESC);
CREATE INDEX IF NOT EXISTS zipper_history_urlkey_idx ON zipper.history (url_key);

-- The same asset grabbed twice should update, not duplicate — that is what
-- makes "already downloaded" answerable with one lookup.
CREATE UNIQUE INDEX IF NOT EXISTS zipper_history_unique_grab
    ON zipper.history (domain, url_key);

-- ------------------------------------------------------- site profiles -----
-- Derived and disposable: deleting a row costs exactly one full scan, which
-- keeps the learned layer safe to reset whenever it misbehaves.

CREATE TABLE IF NOT EXISTS zipper.site_profile (
    domain              TEXT PRIMARY KEY,       -- registrable domain of the PAGE

    -- Learned harvest hints
    accepted_patterns   JSONB NOT NULL DEFAULT '[]'::jsonb,
    rejected_patterns   JSONB NOT NULL DEFAULT '[]'::jsonb,
    learned_upgrades    JSONB NOT NULL DEFAULT '[]'::jsonb,  -- verified thumb->full rewrites
    best_origin         TEXT,                   -- which harvest source usually wins here
    title_source        TEXT,                   -- which title source produced good names

    -- Defaults remembered from what you actually chose
    default_route       TEXT,
    default_scope       TEXT,                   -- picked container selector
    needs_scroll        BOOLEAN NOT NULL DEFAULT FALSE,

    -- Connection policy keys on the ASSET host, not this domain — a 429
    -- belongs to whoever served the bytes. Stored per-host inside the JSON.
    connection_policy   JSONB NOT NULL DEFAULT '{}'::jsonb,

    -- Staleness guard. A learned fast path fails silently when a site changes
    -- its markup, so the profile carries its own confidence and age and gets
    -- revalidated rather than trusted indefinitely.
    confidence          REAL NOT NULL DEFAULT 0,
    scan_count          INTEGER NOT NULL DEFAULT 0,
    last_full_scan      TIMESTAMPTZ,
    last_full_count     INTEGER,
    last_fast_count     INTEGER,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- -------------------------------------------------------------- quotas -----
-- Checked BEFORE dispatch. A refusal names the limit and its reset, because a
-- silent queue is how a stingy Usenet provider costs you the account.

CREATE TABLE IF NOT EXISTS zipper.quota (
    provider    TEXT NOT NULL,                  -- realdebrid|alldebrid|torbox|sabnzbd|qbit-local|...
    day         DATE NOT NULL,
    grabs       INTEGER NOT NULL DEFAULT 0,
    bytes       BIGINT  NOT NULL DEFAULT 0,
    PRIMARY KEY (provider, day)
);

CREATE TABLE IF NOT EXISTS zipper.quota_limit (
    provider        TEXT PRIMARY KEY,
    max_grabs_day   INTEGER,                    -- NULL = unlimited
    max_bytes_day   BIGINT,
    enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    note            TEXT,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- --------------------------------------------------------------- rules -----
-- Replaces the hardcoded python-zipper/ prefix: match once, and every download
-- lands in the right folder with a real name.

CREATE TABLE IF NOT EXISTS zipper.rule (
    id              BIGSERIAL PRIMARY KEY,
    priority        INTEGER NOT NULL DEFAULT 100,
    enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    match_domain    TEXT,
    match_kind      TEXT,
    match_min_bytes BIGINT,
    match_url_re    TEXT,
    folder_template TEXT,
    name_template   TEXT,
    route           TEXT,
    category        TEXT,                       -- passed through to the *arr stack
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS zipper_rule_priority_idx ON zipper.rule (enabled, priority);

-- ------------------------------------------------------------ triggers -----

CREATE OR REPLACE FUNCTION zipper.touch_updated_at() RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS zipper_jobs_touch ON zipper.jobs;
CREATE TRIGGER zipper_jobs_touch BEFORE UPDATE ON zipper.jobs
    FOR EACH ROW EXECUTE FUNCTION zipper.touch_updated_at();

DROP TRIGGER IF EXISTS zipper_profile_touch ON zipper.site_profile;
CREATE TRIGGER zipper_profile_touch BEFORE UPDATE ON zipper.site_profile
    FOR EACH ROW EXECUTE FUNCTION zipper.touch_updated_at();

-- Additive columns for tables that already exist in a deployed database.
-- CREATE TABLE IF NOT EXISTS is a no-op there, so new columns need their own
-- statement. Each is IF NOT EXISTS, so this whole file stays re-runnable.
ALTER TABLE zipper.jobs ADD COLUMN IF NOT EXISTS rclone_remotes JSONB NOT NULL DEFAULT '[]'::jsonb;
-- Where a job returns an ANSWER rather than files. A stream probe is the case:
-- the caller needs the format list back before it can choose a quality, so the
-- worker writes yt-dlp's metadata here and the extension reads it off the job.
-- Kept generic rather than a formats column -- the next question a worker
-- answers should not need a migration.
ALTER TABLE zipper.jobs ADD COLUMN IF NOT EXISTS result JSONB;

-- ------------------------------------------------------------- workers -----
-- What each worker is, and how much room it has left.
--
-- Storage is reported *inward* rather than scraped outward, which is the same
-- reason jobs are claimed rather than pushed: a worker may be behind NAT,
-- asleep, or on a tailnet the browser cannot reach, and requiring the API to
-- dial it would make "how full is that disk" work only when everything is up.
-- A worker that has been off for a week still has a last-known report here, and
-- `seen_at` says how much to trust it.
--
-- `rclone_desired` is the other direction: the extension writes the remote
-- priority it wants, the worker picks it up on its next heartbeat and applies
-- it locally. Nothing has to reach into the worker to reconfigure it.

CREATE TABLE IF NOT EXISTS zipper.worker (
    name            TEXT PRIMARY KEY,           -- e.g. zipper@CLOPEUX-DESKTOP
    host            TEXT,
    platform        TEXT,
    version         TEXT,
    dest_dir        TEXT,
    -- Last storage_report(): disk totals, what is still staged locally, and
    -- each configured rclone remote with the provider's own free-space numbers.
    storage         JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- Remote priority the operator has asked for, applied by the worker.
    rclone_desired  JSONB,
    first_seen      TIMESTAMPTZ NOT NULL DEFAULT now(),
    seen_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS zipper_worker_seen_idx ON zipper.worker (seen_at DESC);
