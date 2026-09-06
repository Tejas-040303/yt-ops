-- yt-ops schema v1
-- Model: TOPIC -> SOURCES -> ACCOUNTS (competing versions) -> CLAIMS
--                        \-> ANGLES -> SCRIPT -> VIDEO -> ANALYTICS
-- Hierarchy lives in foreign keys. Files get a flat readable code.

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------
-- 1. TOPIC : one research effort. Produces many videos.
-- ---------------------------------------------------------------
CREATE TABLE topics (
    id           INTEGER PRIMARY KEY,
    slug         TEXT NOT NULL UNIQUE,          -- 'earth-age'
    title        TEXT NOT NULL,                 -- 'How we learned the age of the Earth'
    status       TEXT NOT NULL DEFAULT 'new',   -- new | researching | ready | exhausted | rejected
    reject_note  TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    researched_at TEXT
);

-- ---------------------------------------------------------------
-- 2. SOURCE : a document found during research. Never deleted.
-- ---------------------------------------------------------------
CREATE TABLE sources (
    id           INTEGER PRIMARY KEY,
    topic_id     INTEGER NOT NULL REFERENCES topics(id),
    url          TEXT NOT NULL,
    title        TEXT,
    publisher    TEXT,                          -- 'Stanford Encyclopedia of Philosophy'
    kind         TEXT NOT NULL,                 -- primary | scholarly | encyclopedia | museum | popular | unknown
    credibility  TEXT NOT NULL DEFAULT 'medium',-- high | medium | low
    published    TEXT,                          -- date of the source itself, if known
    retrieved_at TEXT NOT NULL DEFAULT (datetime('now')),
    local_path   TEXT,                          -- cached copy; sources vanish
    UNIQUE(topic_id, url)
);

-- ---------------------------------------------------------------
-- 3. ACCOUNT : a competing version of the story. Your v1 / v2 idea.
--    Labelled by stance, not by number.
-- ---------------------------------------------------------------
CREATE TABLE accounts (
    id         INTEGER PRIMARY KEY,
    topic_id   INTEGER NOT NULL REFERENCES topics(id),
    stance     TEXT NOT NULL,                   -- popular | consensus | disputed | superseded | fringe
    label      TEXT NOT NULL,                   -- short human name: 'Newton's apple'
    summary    TEXT NOT NULL,                   -- 2-4 sentences of what this version says
    confidence TEXT NOT NULL DEFAULT 'medium',  -- high | medium | low
    notes      TEXT
);
CREATE INDEX idx_accounts_topic ON accounts(topic_id);

-- ---------------------------------------------------------------
-- 4. CLAIM : one checkable assertion belonging to an account.
-- ---------------------------------------------------------------
CREATE TABLE claims (
    id         INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL REFERENCES accounts(id),
    text       TEXT NOT NULL,
    verdict    TEXT NOT NULL DEFAULT 'uncertain', -- verified | probable | uncertain | disputed | false
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_claims_account ON claims(account_id);

-- Which source supports or contradicts which claim.
CREATE TABLE claim_sources (
    claim_id  INTEGER NOT NULL REFERENCES claims(id),
    source_id INTEGER NOT NULL REFERENCES sources(id),
    direction INTEGER NOT NULL,                 -- 1 supports, -1 contradicts, 0 mentions
    quote     TEXT,                             -- the supporting line, for your own audit
    PRIMARY KEY (claim_id, source_id)
);

-- ---------------------------------------------------------------
-- 5. ANGLE : a standalone video idea derived from a topic.
--    Replaces "part 1 / part 2". Each angle must stand alone.
-- ---------------------------------------------------------------
CREATE TABLE angles (
    id          INTEGER PRIMARY KEY,
    topic_id    INTEGER NOT NULL REFERENCES topics(id),
    account_id  INTEGER REFERENCES accounts(id),  -- which version this angle leans on
    kind        TEXT NOT NULL,                    -- myth_bust | origin | mechanism | person | consequence | unknown_still
    hook        TEXT NOT NULL,                    -- the first sentence, written first
    status      TEXT NOT NULL DEFAULT 'idea',     -- idea | scripted | rendered | published | killed
    planned_for TEXT,                             -- yyyy-mm-dd
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_angles_topic ON angles(topic_id);

-- ---------------------------------------------------------------
-- 6. SCRIPT
-- ---------------------------------------------------------------
CREATE TABLE scripts (
    id            INTEGER PRIMARY KEY,
    angle_id      INTEGER NOT NULL REFERENCES angles(id),
    body          TEXT NOT NULL,
    word_count    INTEGER,
    duration_est  REAL,
    format        TEXT,                          -- story_reveal | myth_reality | question_answer | three_facts
    has_person    INTEGER DEFAULT 0,             -- channel rule gate
    has_place     INTEGER DEFAULT 0,
    has_year      INTEGER DEFAULT 0,
    rejected      INTEGER DEFAULT 0,
    reject_reason TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------
-- 7. VIDEO
-- ---------------------------------------------------------------
CREATE TABLE videos (
    id           INTEGER PRIMARY KEY,
    script_id    INTEGER NOT NULL REFERENCES scripts(id),
    code         TEXT NOT NULL UNIQUE,           -- '0042-earth-age-myth-bust'
    file_path    TEXT,
    title        TEXT,
    description  TEXT,
    hashtags     TEXT,
    duration     REAL,
    qc_passed    INTEGER DEFAULT 0,
    youtube_id   TEXT,                           -- filled in after YOU upload manually
    published_at TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------
-- 8. ASSET : every visual/audio element, with its licence.
--    No row = it does not go in the video.
-- ---------------------------------------------------------------
CREATE TABLE assets (
    id                  INTEGER PRIMARY KEY,
    video_id            INTEGER NOT NULL REFERENCES videos(id),
    local_path          TEXT NOT NULL,
    source_url          TEXT NOT NULL,
    creator             TEXT,
    license             TEXT NOT NULL,           -- public_domain | cc0 | cc_by | cc_by_sa | pexels | generated | original
    commercial_ok       INTEGER NOT NULL,        -- 0 = REJECT
    attribution_required INTEGER NOT NULL DEFAULT 0,
    attribution_text    TEXT,
    acquired_at         TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ---------------------------------------------------------------
-- 9. MYTH BLACKLIST : grows forever. Checked before every script.
-- ---------------------------------------------------------------
CREATE TABLE myth_blacklist (
    id              INTEGER PRIMARY KEY,
    myth            TEXT NOT NULL,
    why_wrong       TEXT NOT NULL,
    correct_version TEXT,
    source_url      TEXT,
    added_at        TEXT NOT NULL DEFAULT (datetime('now'))
);

INSERT INTO myth_blacklist (myth, why_wrong) VALUES
 ('Newton was hit on the head by a falling apple',
  'Newton described watching an apple fall, via Stukeley. No head, no eureka moment.'),
 ('Galileo dropped balls from the Leaning Tower of Pisa',
  'No contemporary record. The story comes from Viviani, written decades later.'),
 ('Einstein failed mathematics at school',
  'He excelled at mathematics. The myth stems from a misread Swiss grading scale.'),
 ('Columbus proved the Earth was round',
  'Educated Europeans had accepted a spherical Earth since antiquity. The dispute was its size.'),
 ('Edison invented the light bulb',
  'He produced a commercially viable version. Incandescent lamps predate him by decades.'),
 ('Darwin had a sudden insight from Galapagos finches',
  'He did not identify them properly until after returning; the theory developed over years.'),
 ('Medieval people believed the Earth was flat',
  'A 19th-century invention, largely traceable to Washington Irving and later polemics.'),
 ('Vikings wore horned helmets',
  'No archaeological support. Popularised by 19th-century opera costume design.');

-- ---------------------------------------------------------------
-- 10. ANALYTICS : one row per video per day. Never deleted.
-- ---------------------------------------------------------------
CREATE TABLE analytics_daily (
    video_id           INTEGER NOT NULL REFERENCES videos(id),
    day                TEXT NOT NULL,            -- yyyy-mm-dd
    views              INTEGER,
    engaged_views      INTEGER,
    avg_view_duration  REAL,
    avg_pct_viewed     REAL,
    likes              INTEGER,
    comments           INTEGER,
    shares             INTEGER,
    subs_gained        INTEGER,
    subs_lost          INTEGER,
    PRIMARY KEY (video_id, day)
);

-- ---------------------------------------------------------------
-- 11. JOBS + ERRORS : minimal ops tracking.
-- ---------------------------------------------------------------
CREATE TABLE jobs (
    id         INTEGER PRIMARY KEY,
    kind       TEXT NOT NULL,                    -- research | script | render | analytics
    ref_id     INTEGER,
    status     TEXT NOT NULL DEFAULT 'queued',   -- queued | running | done | failed
    attempts   INTEGER DEFAULT 0,
    error      TEXT,
    started_at TEXT,
    ended_at   TEXT
);

-- ---------------------------------------------------------------
-- The questions this schema exists to answer:
-- ---------------------------------------------------------------
-- Which angle kind retains best?
--   SELECT a.kind, AVG(d.avg_pct_viewed) FROM angles a
--   JOIN scripts s ON s.angle_id=a.id JOIN videos v ON v.script_id=s.id
--   JOIN analytics_daily d ON d.video_id=v.id GROUP BY a.kind;
--
-- Which topics are not exhausted yet?
--   SELECT t.slug, COUNT(a.id) FROM topics t LEFT JOIN angles a ON a.topic_id=t.id
--   WHERE t.status='ready' GROUP BY t.slug HAVING COUNT(a.id) < 4;
--
-- Any published claim resting on a single low-credibility source?
--   SELECT c.text FROM claims c JOIN claim_sources cs ON cs.claim_id=c.id
--   JOIN sources s ON s.id=cs.source_id
--   GROUP BY c.id HAVING COUNT(*)=1 AND MAX(s.credibility)='low';
