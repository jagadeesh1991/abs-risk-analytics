-- ============================================================================
-- Structured Products Risk Analytics Engine — PostgreSQL schema
-- Requires: PostgreSQL 15+, TimescaleDB extension for loan_level_performance.
-- Conventions: rates are annual decimals (0.065 = 6.5%); money is NUMERIC(18,2);
-- all timestamps UTC.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ----------------------------------------------------------------------------
-- Deal library
-- ----------------------------------------------------------------------------
CREATE TABLE deals (
    deal_id         BIGSERIAL PRIMARY KEY,
    deal_name       TEXT        NOT NULL UNIQUE,
    asset_class     TEXT        NOT NULL CHECK (asset_class IN ('ABS','CLO','MBS','RMBS','CMBS')),
    issuer          TEXT,
    closing_date    DATE        NOT NULL,
    first_pay_date  DATE        NOT NULL,
    maturity_date   DATE,
    payment_freq    SMALLINT    NOT NULL DEFAULT 12,          -- payments per year
    day_count       TEXT        NOT NULL DEFAULT '30/360'
                                CHECK (day_count IN ('30/360','ACT/360','ACT/365')),
    -- declarative structural features: triggers, fees, reserve accounts,
    -- payment rules. Interpreted by the waterfall engine; versioned.
    structure       JSONB       NOT NULL DEFAULT '{}'::jsonb,
    structure_ver   INTEGER     NOT NULL DEFAULT 1,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE tranches (
    tranche_id      BIGSERIAL PRIMARY KEY,
    deal_id         BIGINT      NOT NULL REFERENCES deals(deal_id) ON DELETE CASCADE,
    tranche_name    TEXT        NOT NULL,
    cusip           TEXT,
    seniority_rank  SMALLINT    NOT NULL,                     -- 1 = most senior
    orig_balance    NUMERIC(18,2) NOT NULL CHECK (orig_balance >= 0),
    curr_balance    NUMERIC(18,2) NOT NULL CHECK (curr_balance >= 0),
    coupon_type     TEXT        NOT NULL CHECK (coupon_type IN ('FIXED','FLOATING')),
    fixed_rate      NUMERIC(9,6),                             -- when FIXED
    float_index     TEXT,                                     -- e.g. 'SOFR' when FLOATING
    float_margin    NUMERIC(9,6),                             -- spread over index
    rate_cap        NUMERIC(9,6),
    rate_floor      NUMERIC(9,6) DEFAULT 0,
    payment_freq    SMALLINT    NOT NULL DEFAULT 12,
    orig_rating     TEXT,
    UNIQUE (deal_id, tranche_name),
    UNIQUE (deal_id, seniority_rank),
    CHECK ( (coupon_type = 'FIXED'    AND fixed_rate  IS NOT NULL)
         OR (coupon_type = 'FLOATING' AND float_index IS NOT NULL
                                      AND float_margin IS NOT NULL) )
);
CREATE INDEX idx_tranches_deal ON tranches(deal_id, seniority_rank);

-- ----------------------------------------------------------------------------
-- Collateral
-- ----------------------------------------------------------------------------
CREATE TABLE collateral_pools (
    pool_id         BIGSERIAL PRIMARY KEY,
    deal_id         BIGINT      REFERENCES deals(deal_id) ON DELETE CASCADE,
    pool_name       TEXT        NOT NULL,
    as_of_date      DATE        NOT NULL,
    loan_count      INTEGER     NOT NULL,
    balance         NUMERIC(18,2) NOT NULL,
    wac             NUMERIC(9,6)  NOT NULL,                   -- wtd-avg gross coupon
    wam_months      SMALLINT    NOT NULL,                     -- wtd-avg remaining maturity
    wala_months     SMALLINT,                                 -- wtd-avg loan age
    wa_fico         NUMERIC(6,1),
    wa_ltv          NUMERIC(6,2),
    wa_dti          NUMERIC(6,2),
    servicing_fee   NUMERIC(9,6) NOT NULL DEFAULT 0.0050,
    geo_distribution JSONB      NOT NULL DEFAULT '{}'::jsonb, -- {"CA": 0.117, ...}
    strat_summary    JSONB      NOT NULL DEFAULT '{}'::jsonb, -- fico/ltv band cuts
    UNIQUE (deal_id, pool_name, as_of_date)
);
CREATE INDEX idx_pools_deal_asof ON collateral_pools(deal_id, as_of_date DESC);

-- REMIC/MBS monthly factor ladder; realized speeds backed out of factor deltas.
CREATE TABLE pool_factors (
    pool_id         BIGINT      NOT NULL REFERENCES collateral_pools(pool_id) ON DELETE CASCADE,
    factor_date     DATE        NOT NULL,
    factor          NUMERIC(12,10) NOT NULL CHECK (factor >= 0 AND factor <= 1),
    cpr_1m          NUMERIC(9,6),                             -- realized, annualized
    cdr_1m          NUMERIC(9,6),
    severity_3m     NUMERIC(9,6),
    source          TEXT        NOT NULL DEFAULT 'trustee',
    source_rank     SMALLINT    NOT NULL DEFAULT 1,           -- higher wins on conflict
    PRIMARY KEY (pool_id, factor_date)
);

-- ----------------------------------------------------------------------------
-- Loan-level performance (TimescaleDB hypertable; mirrors the app's canonical
-- loan schema so servicer tapes flow straight in via the normalizer)
-- ----------------------------------------------------------------------------
CREATE TABLE loan_level_performance (
    pool_id          BIGINT      NOT NULL REFERENCES collateral_pools(pool_id),
    loan_id          TEXT        NOT NULL,
    as_of_date       DATE        NOT NULL,
    origination_date DATE        NOT NULL,
    original_balance NUMERIC(18,2) NOT NULL,
    current_balance  NUMERIC(18,2) NOT NULL,
    interest_rate    NUMERIC(9,6),
    remaining_term   SMALLINT,
    fico             SMALLINT,
    ltv              NUMERIC(6,2),
    dti              NUMERIC(6,2),
    state            CHAR(2),
    days_past_due    SMALLINT    NOT NULL DEFAULT 0,
    dpd_bucket       TEXT        NOT NULL DEFAULT 'CURRENT'
                     CHECK (dpd_bucket IN ('CURRENT','DPD30','DPD60','DPD90','DEFAULT','PREPAID')),
    PRIMARY KEY (pool_id, loan_id, as_of_date)
);
SELECT create_hypertable('loan_level_performance', 'as_of_date',
                         chunk_time_interval => INTERVAL '1 month');
CREATE INDEX idx_llp_bucket ON loan_level_performance(pool_id, as_of_date, dpd_bucket);

-- ----------------------------------------------------------------------------
-- Scenario & simulation results
-- ----------------------------------------------------------------------------
CREATE TABLE scenarios (
    scenario_id     BIGSERIAL PRIMARY KEY,
    scenario_name   TEXT        NOT NULL UNIQUE,
    -- assumption vectors: {"cpr": [...] | 0.08, "cdr": ..., "severity": 0.4,
    --                      "recovery_lag": 6, "curve_shift_bps": 0}
    assumptions     JSONB       NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE simulation_runs (
    run_id          BIGSERIAL PRIMARY KEY,
    deal_id         BIGINT      NOT NULL REFERENCES deals(deal_id),
    scenario_id     BIGINT      NOT NULL REFERENCES scenarios(scenario_id),
    curve_date      DATE        NOT NULL,
    status          TEXT        NOT NULL DEFAULT 'PENDING'
                    CHECK (status IN ('PENDING','RUNNING','DONE','FAILED')),
    engine_version  TEXT        NOT NULL,
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    -- headline outputs per tranche: {"Class A": {"pv":..., "eff_duration":...,
    --  "wal_years":..., "writedown":...}, "__residual__": {...}}
    metrics         JSONB       NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (deal_id, scenario_id, curve_date, engine_version)   -- idempotent reruns
);

-- one row per tranche-period; the full projected cash-flow tape of a run
CREATE TABLE tranche_cashflows (
    run_id          BIGINT      NOT NULL REFERENCES simulation_runs(run_id) ON DELETE CASCADE,
    tranche_id      BIGINT      NOT NULL REFERENCES tranches(tranche_id),
    period          SMALLINT    NOT NULL,                     -- 1..n months
    begin_balance   NUMERIC(18,2) NOT NULL,
    coupon_rate     NUMERIC(9,6)  NOT NULL,
    interest_due    NUMERIC(18,2) NOT NULL,
    interest_paid   NUMERIC(18,2) NOT NULL,
    interest_short  NUMERIC(18,2) NOT NULL,
    principal_paid  NUMERIC(18,2) NOT NULL,
    turbo_principal NUMERIC(18,2) NOT NULL DEFAULT 0,
    writedown       NUMERIC(18,2) NOT NULL DEFAULT 0,
    end_balance     NUMERIC(18,2) NOT NULL,
    PRIMARY KEY (run_id, tranche_id, period)
);
