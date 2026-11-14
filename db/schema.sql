-- Схема платформы бронирования «СПА-парк».
-- Защита от накладок: EXCLUDE-ограничения по пересечению интервалов
-- для пространства (с учётом уборки) и для мастера (только время программы).

CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE IF NOT EXISTS spaces (
    id          serial PRIMARY KEY,
    code        text UNIQUE NOT NULL,
    name        text NOT NULL,
    name_en     text NOT NULL,
    description text NOT NULL DEFAULT '',
    description_en text NOT NULL DEFAULT '',
    is_relax    boolean NOT NULL DEFAULT false,
    sort        int NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS masters (
    id     serial PRIMARY KEY,
    name   text NOT NULL,
    skills text NOT NULL DEFAULT '',
    active boolean NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS programs (
    id           serial PRIMARY KEY,
    code         text UNIQUE NOT NULL,
    space_id     int NOT NULL REFERENCES spaces(id),
    name         text NOT NULL,
    name_en      text NOT NULL,
    description  text NOT NULL DEFAULT '',
    description_en text NOT NULL DEFAULT '',
    duration_min int NOT NULL CHECK (duration_min > 0),
    master_min   int NOT NULL CHECK (master_min > 0),
    cleanup_min  int NOT NULL DEFAULT 15 CHECK (cleanup_min >= 0),
    price        int CHECK (price >= 0),
    price_couple int CHECK (price_couple >= 0),
    max_guests   int NOT NULL DEFAULT 2,
    prepay       boolean NOT NULL DEFAULT false,
    tags         text NOT NULL DEFAULT '',
    active       boolean NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS guests (
    id            serial PRIMARY KEY,
    phone         text UNIQUE,
    name          text,
    birth_date    date,
    max_user_id   bigint UNIQUE,
    max_chat_id   bigint,
    lang          text NOT NULL DEFAULT 'ru',
    loyalty_card  text UNIQUE,
    loyalty_points int NOT NULL DEFAULT 0,
    unsubscribed  boolean NOT NULL DEFAULT false,
    deleted_at    timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now()
);

-- Версии текстов согласий: что именно подтверждал гость.
CREATE TABLE IF NOT EXISTS consent_texts (
    version    text NOT NULL,
    kind       text NOT NULL CHECK (kind IN ('pd', 'ads', 'rules')),
    text       text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (version, kind)
);

-- Журнал доступа к персональным данным (кто, когда, к чьим данным, что сделал).
CREATE TABLE IF NOT EXISTS pd_access_log (
    id         bigserial PRIMARY KEY,
    actor      text NOT NULL,
    action     text NOT NULL,
    guest_id   int,
    details    text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Согласия: факт, дата/время, версия текста, канал.
CREATE TABLE IF NOT EXISTS consents (
    id           serial PRIMARY KEY,
    guest_id     int NOT NULL REFERENCES guests(id),
    kind         text NOT NULL CHECK (kind IN ('pd', 'ads', 'rules')),
    granted      boolean NOT NULL,
    text_version text NOT NULL,
    channel      text NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS consents_guest ON consents (guest_id, kind, created_at DESC);

CREATE TABLE IF NOT EXISTS bookings (
    id              serial PRIMARY KEY,
    guest_id        int NOT NULL REFERENCES guests(id),
    program_id      int NOT NULL REFERENCES programs(id),
    space_id        int NOT NULL REFERENCES spaces(id),
    master_id       int NOT NULL REFERENCES masters(id),
    starts_at       timestamptz NOT NULL,
    ends_at         timestamptz NOT NULL,
    master_until    timestamptz NOT NULL,
    busy_until      timestamptz NOT NULL,
    status          text NOT NULL CHECK (status IN ('hold', 'confirmed', 'cancelled', 'expired', 'completed', 'no_show')),
    source          text NOT NULL CHECK (source IN ('bot', 'admin', 'web')),
    hold_expires_at timestamptz,
    hold_warned     boolean NOT NULL DEFAULT false,
    visit_status    text NOT NULL DEFAULT 'none' CHECK (visit_status IN ('none', 'asked', 'confirmed', 'declined')),
    payment_status  text NOT NULL DEFAULT 'unpaid' CHECK (payment_status IN ('unpaid', 'prepaid', 'paid', 'certificate')),
    payment_method  text,
    guests_count    int NOT NULL DEFAULT 1,
    price_total     int NOT NULL DEFAULT 0,
    note            text NOT NULL DEFAULT '',
    created_at      timestamptz NOT NULL DEFAULT now(),
    confirmed_at    timestamptz,
    CHECK (ends_at > starts_at AND busy_until >= ends_at),
    CHECK (status <> 'hold' OR hold_expires_at IS NOT NULL),
    CONSTRAINT no_space_overlap EXCLUDE USING gist (
        space_id WITH =, tstzrange(starts_at, busy_until) WITH &&
    ) WHERE (status IN ('hold', 'confirmed')),
    CONSTRAINT no_master_overlap EXCLUDE USING gist (
        master_id WITH =, tstzrange(starts_at, master_until) WITH &&
    ) WHERE (status IN ('hold', 'confirmed'))
);
-- Один активный захват на гостя.
CREATE UNIQUE INDEX IF NOT EXISTS one_hold_per_guest ON bookings (guest_id) WHERE status = 'hold';
CREATE INDEX IF NOT EXISTS bookings_day ON bookings (starts_at);

CREATE TABLE IF NOT EXISTS preorder_items (
    id       serial PRIMARY KEY,
    name     text NOT NULL,
    name_en  text NOT NULL,
    category text NOT NULL CHECK (category IN ('tea', 'bath', 'extra')),
    price    int NOT NULL DEFAULT 0,
    stock    int NOT NULL DEFAULT 0,
    active   boolean NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS program_preorders (
    program_id int NOT NULL REFERENCES programs(id),
    item_id    int NOT NULL REFERENCES preorder_items(id),
    PRIMARY KEY (program_id, item_id)
);

CREATE TABLE IF NOT EXISTS booking_preorders (
    booking_id int NOT NULL REFERENCES bookings(id) ON DELETE CASCADE,
    item_id    int NOT NULL REFERENCES preorder_items(id),
    qty        int NOT NULL DEFAULT 1 CHECK (qty > 0),
    PRIMARY KEY (booking_id, item_id)
);

-- Состояние диалога гостя с ассистентом.
CREATE TABLE IF NOT EXISTS sessions (
    guest_id      int PRIMARY KEY REFERENCES guests(id),
    state         jsonb NOT NULL DEFAULT '{}'::jsonb,
    misunderstood int NOT NULL DEFAULT 0,
    updated_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS messages (
    id         bigserial PRIMARY KEY,
    guest_id   int NOT NULL REFERENCES guests(id),
    role       text NOT NULL CHECK (role IN ('guest', 'bot', 'admin')),
    text       text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS messages_guest ON messages (guest_id, id);

CREATE TABLE IF NOT EXISTS escalations (
    id             serial PRIMARY KEY,
    guest_id       int NOT NULL REFERENCES guests(id),
    reason         text NOT NULL,
    priority       text NOT NULL CHECK (priority IN ('high', 'normal')),
    details        text NOT NULL DEFAULT '',
    status         text NOT NULL DEFAULT 'new' CHECK (status IN ('new', 'accepted', 'closed')),
    notified_count int NOT NULL DEFAULT 0,
    last_notified  timestamptz,
    created_at     timestamptz NOT NULL DEFAULT now(),
    accepted_at    timestamptz
);

CREATE TABLE IF NOT EXISTS campaigns (
    id         serial PRIMARY KEY,
    name       text NOT NULL,
    segment    text NOT NULL,
    template   text NOT NULL,
    status     text NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'sent')),
    created_at timestamptz NOT NULL DEFAULT now(),
    sent_at    timestamptz
);

-- Исходящие сообщения (журнал рассылок, напоминаний, уведомлений).
CREATE TABLE IF NOT EXISTS outbox (
    id          bigserial PRIMARY KEY,
    guest_id    int REFERENCES guests(id),
    kind        text NOT NULL,
    text        text NOT NULL,
    campaign_id int REFERENCES campaigns(id),
    booking_id  int REFERENCES bookings(id),
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS outbox_once ON outbox (kind, booking_id) WHERE booking_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS job_runs (
    job     text NOT NULL,
    run_day date NOT NULL,
    PRIMARY KEY (job, run_day)
);
