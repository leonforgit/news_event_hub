-- =============================================================================
-- news_event.db  Schema v1
-- News Event Hub 共享新闻/事件底座
-- 运行位: private runtime
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. SOURCE REGISTRY
--    统一管理所有新闻源。下游 collector 写入时必须带有 source_id。
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS source_registry (
    source_id           TEXT PRIMARY KEY,           -- e.g. "akshare_news_cctv", "polymarket"
    name                TEXT NOT NULL,              -- 人类可读名称
    lane                TEXT NOT NULL               -- 'confirmation' | 'signal'
                            CHECK (lane IN ('confirmation', 'signal')),
    source_family       TEXT,                       -- 证据传播链 / 原始来源族，如 'wire:prnewswire'
    source_type         TEXT NOT NULL,              -- 'api' | 'rss' | 'scrape' | 'social' | 'exchange'
    trust_tier          INTEGER NOT NULL DEFAULT 2  -- 1=最高信任, 2=普通, 3=低信任/舆论
                            CHECK (trust_tier IN (1, 2, 3)),
    coverage_scope      TEXT,                       -- 'macro' | 'industry' | 'company' | 'global' | 'mixed'
    collector_owner     TEXT,                       -- 'radar' | 'daily_report' | 'research' | 'shared'
    scheduler_class     TEXT,                       -- 'high_freq' | 'daily' | 'on_demand'
    origin_system       TEXT,                       -- 'investment_report' | 'industry_signal_radar' | 'news_event_hub'
    legacy_key          TEXT,                       -- 旧系统中的 source key / source id
    phase1_disposition  TEXT NOT NULL DEFAULT 'migrate_phase1'
                            CHECK (phase1_disposition IN ('migrate_phase1', 'compat_keep', 'defer', 'exclude')),
    enabled             INTEGER NOT NULL DEFAULT 1  -- 0=禁用, 1=启用
                            CHECK (enabled IN (0, 1)),
    description         TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_source_lane    ON source_registry (lane);
CREATE INDEX IF NOT EXISTS idx_source_enabled ON source_registry (enabled);
CREATE INDEX IF NOT EXISTS idx_source_origin  ON source_registry (origin_system);
CREATE INDEX IF NOT EXISTS idx_source_legacy  ON source_registry (legacy_key);


-- -----------------------------------------------------------------------------
-- 2. NEWS_ARTICLES
--    标准化文章层。所有 collector 的输出都必须写到这里。
--    content_hash 用于 source 内去重，不应吞掉跨 source 的确认关系。
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS news_articles (
    article_id              TEXT PRIMARY KEY,       -- uuid 或 hash-based id
    source_id               TEXT NOT NULL
                                REFERENCES source_registry (source_id),
    title                   TEXT NOT NULL,
    title_norm              TEXT,                   -- 清洗后标题，用于相似度比较
    summary                 TEXT,
    body_text               TEXT,
    url                     TEXT,
    canonical_url           TEXT,                   -- 去参数后的规范 URL
    published_at            TEXT,                   -- ISO 8601，允许 NULL（时间不明）
    timestamp_quality       TEXT NOT NULL DEFAULT 'unknown'
                                CHECK (timestamp_quality IN ('exact', 'estimated', 'unknown')),
    content_hash            TEXT NOT NULL,          -- sha256(title_norm + body_snippet)，去重用
    language                TEXT NOT NULL DEFAULT 'zh',
    collector_scope         TEXT NOT NULL DEFAULT 'baseline_shared'
                                CHECK (collector_scope IN ('baseline_shared', 'baseline_radar', 'targeted_research')),
    -- 文章层 ranking 分值（计算后回写）
    article_rank_score      REAL,
    article_rank_flags      TEXT,                   -- JSON: {"background_penalty": 1.0, ...}
    -- 采集元数据
    collected_at            TEXT NOT NULL DEFAULT (datetime('now')),
    created_at              TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_articles_source_content_hash
    ON news_articles (source_id, content_hash) WHERE content_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_articles_source       ON news_articles (source_id);
CREATE INDEX IF NOT EXISTS idx_articles_source_canonical_collected
    ON news_articles (source_id, canonical_url, collected_at DESC)
    WHERE canonical_url IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_articles_source_url_collected
    ON news_articles (source_id, url, collected_at DESC)
    WHERE url IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_articles_source_title_published_collected
    ON news_articles (source_id, title_norm, published_at, collected_at DESC)
    WHERE title_norm IS NOT NULL AND published_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_articles_published    ON news_articles (published_at DESC);
CREATE INDEX IF NOT EXISTS idx_articles_collected    ON news_articles (collected_at DESC);
CREATE INDEX IF NOT EXISTS idx_articles_scope        ON news_articles (collector_scope);


-- -----------------------------------------------------------------------------
-- 3. EVENTS
--    事件层。多篇文章可聚合成同一事件。
--    这是 ranking 和下游消费的核心对象。
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS events (
    event_id            TEXT PRIMARY KEY,           -- uuid
    event_type          TEXT,                       -- 'policy' | 'earnings' | 'supply_chain' |
                                                    -- 'macro_data' | 'market_move' | 'social_signal' | ...
    event_title         TEXT NOT NULL,              -- 人类可读事件标题（由聚类或 LLM 生成）
    topic_key           TEXT,                       -- 长期主线键：company:<slug> / industry:<slug> / macro:<slug>
    event_state         TEXT NOT NULL DEFAULT 'emerging'
                            CHECK (event_state IN ('watch', 'emerging', 'confirmed', 'contested', 'mature', 'closed')),
    first_seen_at       TEXT NOT NULL,              -- 最早相关文章的 published_at
    last_seen_at        TEXT NOT NULL,              -- 最新相关文章的 published_at（随时更新）
    novelty_state       TEXT NOT NULL DEFAULT 'new'
                            CHECK (novelty_state IN ('new', 'developing', 'stale', 'closed')),
    confirmation_count  INTEGER NOT NULL DEFAULT 1, -- 有多少独立源确认了这个事件
    source_mix          TEXT,                       -- JSON: {"confirmation": 3, "signal": 1} 来源分布
    score_vector        TEXT,                       -- JSON: {"market_significance": 0.7, ...}
    calibrated_confirmation REAL,
    uncertainty        REAL,
    article_count_raw   INTEGER NOT NULL DEFAULT 0,
    independent_evidence_count INTEGER NOT NULL DEFAULT 0,
    source_family_count INTEGER NOT NULL DEFAULT 0,
    signal_platform_count INTEGER NOT NULL DEFAULT 0,
    -- 实体与市场映射（轻量冗余，详细映射见 event_entity_links）
    primary_industry    TEXT,                       -- 最主要关联行业
    primary_entity      TEXT,                       -- 最主要关联公司/主题
    -- 事件层 ranking 分值（计算后回写）
    event_rank_score    REAL,
    event_rank_flags    TEXT,                       -- JSON: {"duplicate_event_penalty": 0.5, ...}
    -- 是否已映射到投资机会
    opportunity_state   TEXT DEFAULT 'unreviewed'
                            CHECK (opportunity_state IN ('unreviewed', 'mapped', 'rejected')),
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_events_novelty       ON events (novelty_state);
CREATE INDEX IF NOT EXISTS idx_events_state         ON events (event_state);
CREATE INDEX IF NOT EXISTS idx_events_topic         ON events (topic_key);
CREATE INDEX IF NOT EXISTS idx_events_last_seen     ON events (last_seen_at DESC);
CREATE INDEX IF NOT EXISTS idx_events_rank          ON events (event_rank_score DESC);
CREATE INDEX IF NOT EXISTS idx_events_opportunity   ON events (opportunity_state);


-- -----------------------------------------------------------------------------
-- 4. ARTICLE_EVENT_LINKS
--    文章与事件的多对多关系。
--    一篇文章可以关联到多个事件；一个事件由多篇文章支撑。
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS article_event_links (
    article_id      TEXT NOT NULL REFERENCES news_articles (article_id) ON DELETE CASCADE,
    event_id        TEXT NOT NULL REFERENCES events (event_id) ON DELETE CASCADE,
    link_type       TEXT NOT NULL DEFAULT 'supporting'
                        CHECK (link_type IN ('primary', 'supporting', 'tangential')),
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (article_id, event_id)
);

CREATE INDEX IF NOT EXISTS idx_ael_event    ON article_event_links (event_id);
CREATE INDEX IF NOT EXISTS idx_ael_article  ON article_event_links (article_id);


-- -----------------------------------------------------------------------------
-- 5. EVENT_ENTITY_LINKS
--    事件到实体（行业/公司/主题/宏观主线）的映射层。
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS event_entity_links (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id        TEXT NOT NULL REFERENCES events (event_id) ON DELETE CASCADE,
    entity_type     TEXT NOT NULL
                        CHECK (entity_type IN ('industry', 'company', 'theme', 'macro_theme', 'institution')),
    entity_id       TEXT NOT NULL,              -- 外部 ID，与 watchlist/tracker 对齐
    entity_name     TEXT NOT NULL,              -- 人类可读名称
    relevance_score REAL DEFAULT 1.0,           -- 0.0 ~ 1.0，映射强度
    mapping_reason  TEXT,                       -- primary_entity_extract / industry_keyword_match / preserved_existing_link
    mapping_confidence REAL,                    -- 0.0 ~ 1.0，映射置信度
    mapping_version TEXT,                       -- e.g. mapping_layer_v1
    mapping_source  TEXT,                       -- builder / preserved_existing / manual_review
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_eel_event        ON event_entity_links (event_id);
CREATE INDEX IF NOT EXISTS idx_eel_entity       ON event_entity_links (entity_id);
CREATE INDEX IF NOT EXISTS idx_eel_entity_type  ON event_entity_links (entity_type);


CREATE TABLE IF NOT EXISTS unresolved_event_mappings (
    event_id           TEXT PRIMARY KEY REFERENCES events (event_id) ON DELETE CASCADE,
    topic_key          TEXT,
    event_title        TEXT NOT NULL,
    unresolved_reason  TEXT NOT NULL,           -- no_entity_candidate / weak_mapping_only / review_required
    mapping_version    TEXT NOT NULL DEFAULT 'mapping_layer_v1',
    detected_at        TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at         TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_unresolved_event_mappings_topic
    ON unresolved_event_mappings (topic_key);


CREATE TABLE IF NOT EXISTS event_window_snapshots (
    snapshot_id                  TEXT PRIMARY KEY,
    event_id                     TEXT NOT NULL,
    window_granularity          TEXT NOT NULL,
    window_label                TEXT NOT NULL,
    window_start                TEXT NOT NULL,
    window_end                  TEXT NOT NULL,
    as_of                       TEXT NOT NULL,
    event_type                  TEXT,
    event_title                 TEXT NOT NULL,
    topic_key                   TEXT,
    event_state                 TEXT,
    first_seen_at               TEXT NOT NULL,
    last_seen_at                TEXT NOT NULL,
    novelty_state               TEXT NOT NULL,
    confirmation_count          INTEGER NOT NULL DEFAULT 0,
    source_mix                  TEXT,
    score_vector                TEXT,
    calibrated_confirmation     REAL,
    uncertainty                 REAL,
    article_count_raw           INTEGER NOT NULL DEFAULT 0,
    independent_evidence_count  INTEGER NOT NULL DEFAULT 0,
    source_family_count         INTEGER NOT NULL DEFAULT 0,
    signal_platform_count       INTEGER NOT NULL DEFAULT 0,
    primary_industry            TEXT,
    primary_entity              TEXT,
    event_rank_score            REAL,
    event_rank_flags            TEXT,
    article_ids                 TEXT,
    created_at                  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at                  TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(event_id, window_granularity, window_label)
);

CREATE INDEX IF NOT EXISTS idx_event_window_snapshots_window
    ON event_window_snapshots (window_granularity, window_label, event_rank_score DESC);
CREATE INDEX IF NOT EXISTS idx_event_window_snapshots_topic
    ON event_window_snapshots (topic_key, window_granularity, last_seen_at DESC);


-- -----------------------------------------------------------------------------
-- 6. SOURCE_HEALTH
--    记录每个源的健康状态。运行时定期更新。
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS source_health (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id           TEXT NOT NULL REFERENCES source_registry (source_id),
    checked_at          TEXT NOT NULL DEFAULT (datetime('now')),
    status              TEXT NOT NULL
                            CHECK (status IN ('ok', 'degraded', 'down')),
    articles_last_24h   INTEGER DEFAULT 0,      -- 过去 24h 写入文章数
    last_article_at     TEXT,                   -- 最近一篇文章的 published_at
    error_message       TEXT                    -- 如果 degraded/down，记录错误信息
);

CREATE INDEX IF NOT EXISTS idx_source_health_source ON source_health (source_id, checked_at DESC);


-- -----------------------------------------------------------------------------
-- 7. OPPORTUNITY_SIGNALS  （Phase 3+ 用，当前只建表占位）
--    事件升级为投资机会的信号层。由日报/周报视图消费。
-- -----------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS opportunity_signals (
    opportunity_id      TEXT PRIMARY KEY,           -- uuid
    event_id            TEXT NOT NULL REFERENCES events (event_id),
    opportunity_title   TEXT NOT NULL,
    opportunity_type    TEXT,                       -- macro_monitor | company_research | industry_research | special_situation_review | tracking_update
    opportunity_bucket  TEXT,                       -- macro | industry | company | special_situation | tracking_update
    opportunity_rank    REAL,
    portfolio_relevance REAL DEFAULT 0.0,
    watchlist_relevance REAL DEFAULT 0.0,
    thesis_impact       TEXT,                       -- 'positive' | 'negative' | 'neutral' | 'unclear'
    followup_path       TEXT,                       -- 下一步动作（自由文本或 JSON）
    rank_flags          TEXT,                       -- JSON: {"low_investability_penalty": ...}
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_opp_event    ON opportunity_signals (event_id);
CREATE INDEX IF NOT EXISTS idx_opp_rank     ON opportunity_signals (opportunity_rank DESC);


-- =============================================================================
-- VIEWS
-- 便于下游直接查询，不用每次手写 JOIN
-- =============================================================================

-- 行业雷达视图：按行业聚合近 48h 内的有效事件
CREATE VIEW IF NOT EXISTS v_radar_industry AS
SELECT
    eel.entity_name         AS industry,
    e.event_id,
    e.event_title,
    e.event_rank_score,
    e.event_state,
    e.novelty_state,
    e.confirmation_count,
    e.first_seen_at,
    e.last_seen_at
FROM events e
JOIN event_entity_links eel ON e.event_id = eel.event_id
WHERE
    eel.entity_type = 'industry'
    AND e.novelty_state IN ('new', 'developing')
    AND datetime(e.last_seen_at) >= datetime('now', '-48 hours')
    AND e.event_rank_score >= 20
    AND COALESCE(e.opportunity_state, 'unreviewed') != 'rejected'
ORDER BY eel.entity_name, e.event_rank_score DESC;


-- 日报视图：今日最值得研究的事件（event_rank_score 前排）
CREATE VIEW IF NOT EXISTS v_daily_digest AS
SELECT
    e.event_id,
    e.event_title,
    e.event_type,
    e.event_state,
    e.novelty_state,
    e.confirmation_count,
    e.event_rank_score,
    e.primary_industry,
    e.primary_entity,
    e.first_seen_at,
    e.last_seen_at,
    e.source_mix
FROM events e
WHERE
    e.novelty_state IN ('new', 'developing')
    AND datetime(e.last_seen_at) >= datetime('now', '-24 hours')
    AND e.event_rank_score >= 20
    AND COALESCE(e.opportunity_state, 'unreviewed') != 'rejected'
ORDER BY e.event_rank_score DESC;


-- 文章 + 来源联合视图
CREATE VIEW IF NOT EXISTS v_articles_with_source AS
SELECT
    a.article_id,
    a.title,
    a.published_at,
    a.collected_at,
    a.collector_scope,
    a.article_rank_score,
    a.language,
    s.name          AS source_name,
    s.lane          AS source_lane,
    s.trust_tier,
    s.coverage_scope
FROM news_articles a
JOIN source_registry s ON a.source_id = s.source_id;
