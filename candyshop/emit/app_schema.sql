-- SweetReach application database (PostgreSQL).
-- The product helps candy shops find local buyers (schools, weddings, offices...), run campaigns
-- to them, and take bulk / gift / event orders.

DROP SCHEMA IF EXISTS app CASCADE;
CREATE SCHEMA app;
SET search_path = app;

CREATE TABLE plans (
    plan_id             text PRIMARY KEY,
    name                text NOT NULL,
    monthly_price_cents integer NOT NULL,
    annual_price_cents  integer NOT NULL,
    lead_limit          integer NOT NULL,   -- leads surfaced per month
    campaign_limit      integer NOT NULL,   -- campaigns per month
    seat_limit          integer NOT NULL
);

CREATE TABLE products (
    product_id  integer PRIMARY KEY,
    sku         text NOT NULL UNIQUE,
    name        text NOT NULL,
    category    text NOT NULL,
    list_price  numeric(8,2) NOT NULL,
    unit_cost   numeric(8,2),
    season      text                         -- comma-separated month numbers, NULL = year-round
);

-- One row per candy shop using the app.
CREATE TABLE accounts (
    account_id          integer PRIMARY KEY,
    name                text NOT NULL,
    slug                text NOT NULL UNIQUE,
    plan_id             text NOT NULL REFERENCES plans,
    status              text NOT NULL CHECK (status IN ('trialing', 'active', 'past_due', 'churned', 'merged')),
    signup_source       text NOT NULL CHECK (signup_source IN ('sales_assisted', 'self_serve')),
    shop_type           text,
    city                text,
    state               char(2),
    postal_code         text,
    timezone            text,
    employees           integer,
    billing_customer_id text UNIQUE,         -- billing system id; NULL until the trial converts
    created_at          timestamptz NOT NULL,
    trial_ends_at       timestamptz,
    churned_at          timestamptz,
    churn_reason        text,                    -- what customer success recorded; NULL / 'other' are common
    merged_into_account_id integer REFERENCES accounts,   -- set when a duplicate sign-up was merged away
    deleted_at          timestamptz,
    settings            jsonb NOT NULL DEFAULT '{}',
    updated_at          timestamptz NOT NULL
);

CREATE TABLE users (
    user_id       integer PRIMARY KEY,
    account_id    integer NOT NULL REFERENCES accounts,
    email         text NOT NULL,
    full_name     text NOT NULL,
    role          text NOT NULL CHECK (role IN ('owner', 'manager', 'staff')),
    is_active     boolean NOT NULL DEFAULT true,
    created_at    timestamptz NOT NULL,
    last_login_at timestamptz,
    updated_at    timestamptz NOT NULL
);

-- Potential buyers the app finds for a shop (school PTAs, wedding planners, offices...).
CREATE TABLE leads (
    lead_id          integer PRIMARY KEY,
    account_id       integer NOT NULL REFERENCES accounts,
    assigned_user_id integer REFERENCES users,
    org_name         text NOT NULL,
    contact_name     text,
    lead_type        text NOT NULL,
    source           text NOT NULL,
    city             text,
    state            char(2),
    postal_code      text,
    score            integer CHECK (score BETWEEN 0 AND 100),
    status           text NOT NULL CHECK (status IN ('new', 'contacted', 'quoted', 'won', 'lost')),
    est_order_value  numeric(10,2),
    notes            text,                    -- free text typed by the shop's staff
    created_at       timestamptz NOT NULL,
    updated_at       timestamptz NOT NULL,
    attributes       jsonb NOT NULL DEFAULT '{}'
);

CREATE TABLE campaigns (
    campaign_id        integer PRIMARY KEY,
    account_id         integer NOT NULL REFERENCES accounts,
    created_by_user_id integer REFERENCES users,
    name               text NOT NULL,
    channel            text NOT NULL CHECK (channel IN ('email', 'sms', 'social', 'direct_mail')),
    season_tag         text,
    status             text NOT NULL,
    audience_size      integer NOT NULL,
    delivered          integer,
    opens              integer,              -- NULL for channels that do not report opens
    clicks             integer,
    unsubscribes       integer,
    sent_at            timestamptz,
    created_at         timestamptz NOT NULL,
    audience_filter    jsonb NOT NULL DEFAULT '{}'
);

CREATE TABLE orders (
    order_id    integer PRIMARY KEY,
    account_id  integer NOT NULL REFERENCES accounts,
    lead_id     integer REFERENCES leads,        -- set when the order came from a won lead
    campaign_id integer REFERENCES campaigns,    -- set when a campaign click led to the order
    ordered_at  timestamptz NOT NULL,
    order_type  text NOT NULL CHECK (order_type IN ('retail', 'bulk', 'gift_box', 'wholesale', 'event')),
    channel     text NOT NULL,
    status      text NOT NULL CHECK (status IN ('processing', 'fulfilled', 'refunded', 'cancelled')),
    subtotal    numeric(10,2) NOT NULL,
    discount    numeric(10,2) NOT NULL DEFAULT 0,
    total       numeric(10,2) NOT NULL,
    item_count  integer NOT NULL,
    updated_at  timestamptz NOT NULL
);

CREATE TABLE order_items (
    order_item_id integer PRIMARY KEY,
    order_id      integer NOT NULL REFERENCES orders,
    product_id    integer NOT NULL REFERENCES products,
    quantity      integer NOT NULL CHECK (quantity > 0),
    unit_price    numeric(8,2) NOT NULL
);

-- Cancellation form: the dropdown and the free text frequently disagree.
CREATE TABLE exit_surveys (
    survey_id       integer PRIMARY KEY,
    account_id      integer NOT NULL REFERENCES accounts,
    submitted_at    timestamptz NOT NULL,
    reason_code     text NOT NULL,
    would_recommend integer CHECK (would_recommend BETWEEN 0 AND 10),
    free_text       text
);

CREATE TABLE nps_responses (
    response_id  integer PRIMARY KEY,
    account_id   integer NOT NULL REFERENCES accounts,
    user_id      integer REFERENCES users,
    submitted_at timestamptz NOT NULL,
    score        integer NOT NULL CHECK (score BETWEEN 0 AND 10),
    comment      text
);

CREATE INDEX leads_account_idx    ON leads (account_id, created_at);
CREATE INDEX leads_status_idx     ON leads (status);
CREATE INDEX campaigns_account_idx ON campaigns (account_id, sent_at);
CREATE INDEX orders_account_idx   ON orders (account_id, ordered_at);
CREATE INDEX order_items_order_idx ON order_items (order_id);
CREATE INDEX users_account_idx    ON users (account_id);
CREATE INDEX users_email_idx      ON users (lower(email));

-- Handy for the "ask a question" demos: what is each shop doing lately?
CREATE VIEW account_activity_30d AS
SELECT a.account_id, a.name, a.plan_id, a.status,
       count(DISTINCT l.lead_id)  FILTER (WHERE l.created_at >= now() - interval '30 days') AS leads_30d,
       count(DISTINCT c.campaign_id) FILTER (WHERE c.sent_at >= now() - interval '30 days')  AS campaigns_30d,
       count(DISTINCT o.order_id) FILTER (WHERE o.ordered_at >= now() - interval '30 days')  AS orders_30d
FROM accounts a
LEFT JOIN leads l      ON l.account_id = a.account_id
LEFT JOIN campaigns c  ON c.account_id = a.account_id
LEFT JOIN orders o     ON o.account_id = a.account_id
GROUP BY a.account_id, a.name, a.plan_id, a.status;

-- A read-only login for whatever picks this data up. Created once; survives `DROP SCHEMA app`.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'candy_reader') THEN
        CREATE ROLE candy_reader LOGIN PASSWORD 'candy_reader';
    END IF;
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO candy_reader', current_database());
    GRANT USAGE ON SCHEMA app TO candy_reader;
    GRANT SELECT ON ALL TABLES IN SCHEMA app TO candy_reader;
    ALTER DEFAULT PRIVILEGES IN SCHEMA app GRANT SELECT ON TABLES TO candy_reader;
EXCEPTION WHEN insufficient_privilege THEN
    RAISE NOTICE 'could not create or grant the candy_reader role (needs a privileged user)';
END $$;
