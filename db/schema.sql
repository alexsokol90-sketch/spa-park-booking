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

-- Каналы связи гостя (идемпотентные миграции).
ALTER TABLE guests ADD COLUMN IF NOT EXISTS tg_chat_id bigint UNIQUE;
ALTER TABLE guests ADD COLUMN IF NOT EXISTS vk_user_id bigint UNIQUE;

-- Настройки, изменяемые во время работы (например, чат администратора в мессенджере).
CREATE TABLE IF NOT EXISTS settings (
    key   text PRIMARY KEY,
    value text NOT NULL
);

-- График мастеров: смена на день в минутах от полуночи (1440 = 24:00).
-- Ассистент и ресепшен подбирают окна только среди мастеров, стоящих в смене.
CREATE TABLE IF NOT EXISTS master_shifts (
    master_id int NOT NULL REFERENCES masters(id),
    day       date NOT NULL,
    start_min int NOT NULL CHECK (start_min BETWEEN 0 AND 1439),
    end_min   int NOT NULL CHECK (end_min BETWEEN 1 AND 1440),
    note      text NOT NULL DEFAULT '',
    PRIMARY KEY (master_id, day),
    CHECK (end_min > start_min)
);

-- Чек-листы: шаблоны и выполнения (открытие/закрытие смены, подготовка пространства к брони).
CREATE TABLE IF NOT EXISTS checklist_templates (
    id     serial PRIMARY KEY,
    code   text UNIQUE NOT NULL,
    title  text NOT NULL,
    kind   text NOT NULL CHECK (kind IN ('opening', 'closing', 'space', 'custom')),
    items  jsonb NOT NULL,
    active boolean NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS checklist_runs (
    id           serial PRIMARY KEY,
    template_id  int NOT NULL REFERENCES checklist_templates(id),
    day          date NOT NULL,
    booking_id   int REFERENCES bookings(id) ON DELETE CASCADE,
    title        text NOT NULL,
    items        jsonb NOT NULL,
    done         jsonb NOT NULL DEFAULT '{}'::jsonb,
    completed_at timestamptz,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS checklist_runs_once ON checklist_runs (template_id, day, COALESCE(booking_id, 0));

-- Чек-листы: роль исполнителя (администратор, мастер, клининг) и тип запуска (миграция для существующих БД).
ALTER TABLE checklist_templates ADD COLUMN IF NOT EXISTS role text NOT NULL DEFAULT 'admin';
ALTER TABLE checklist_templates ADD COLUMN IF NOT EXISTS sort int NOT NULL DEFAULT 0;
ALTER TABLE checklist_templates DROP CONSTRAINT IF EXISTS checklist_templates_kind_check;
ALTER TABLE checklist_templates ADD CONSTRAINT checklist_templates_kind_check
    CHECK (kind IN ('opening', 'closing', 'daily', 'space', 'cleanup', 'custom'));
ALTER TABLE checklist_templates DROP CONSTRAINT IF EXISTS checklist_templates_role_check;
ALTER TABLE checklist_templates ADD CONSTRAINT checklist_templates_role_check
    CHECK (role IN ('admin', 'master', 'cleaning'));

-- ===== Клиенты и лояльность (миграции) =====
ALTER TABLE guests ADD COLUMN IF NOT EXISTS surname text;
ALTER TABLE guests ADD COLUMN IF NOT EXISTS gender text;
ALTER TABLE guests ADD COLUMN IF NOT EXISTS reg_source text NOT NULL DEFAULT 'messenger';
ALTER TABLE guests ADD COLUMN IF NOT EXISTS reg_channel text NOT NULL DEFAULT 'web';
ALTER TABLE guests ADD COLUMN IF NOT EXISTS referral_code text UNIQUE;
ALTER TABLE guests ADD COLUMN IF NOT EXISTS referred_by int REFERENCES guests(id);
ALTER TABLE guests ADD COLUMN IF NOT EXISTS card_level text NOT NULL DEFAULT 'gold';
ALTER TABLE guests ADD COLUMN IF NOT EXISTS survey_done boolean NOT NULL DEFAULT false;
ALTER TABLE guests DROP CONSTRAINT IF EXISTS guests_gender_check;
ALTER TABLE guests ADD CONSTRAINT guests_gender_check CHECK (gender IS NULL OR gender IN ('f', 'm'));

-- Визит и оплата без кассы: администратор отмечает «пришёл» и сумму.
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS paid_amount int;
ALTER TABLE bookings ADD COLUMN IF NOT EXISTS bonus_spent int NOT NULL DEFAULT 0;

-- Бонусы: каждое движение — отдельная строка (начисление, списание, сгорание, подарок, реферал).
CREATE TABLE IF NOT EXISTS bonus_tx (
    id         bigserial PRIMARY KEY,
    guest_id   int NOT NULL REFERENCES guests(id),
    delta      int NOT NULL,
    kind       text NOT NULL CHECK (kind IN ('accrual', 'redeem', 'expire', 'gift', 'referral', 'adjust')),
    booking_id int REFERENCES bookings(id),
    expires_at timestamptz,
    note       text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS bonus_tx_guest ON bonus_tx (guest_id, created_at);

-- Подарочные сертификаты: номер, номинал, остаток, движения.
CREATE TABLE IF NOT EXISTS certificates (
    id           serial PRIMARY KEY,
    number       text UNIQUE NOT NULL,
    kind         text NOT NULL CHECK (kind IN ('nominal', 'program')),
    program_name text,
    amount       int NOT NULL CHECK (amount > 0),
    balance      int NOT NULL CHECK (balance >= 0),
    status       text NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'used', 'expired', 'cancelled')),
    buyer_name   text,
    buyer_phone  text,
    owner_name   text,
    sold_at      timestamptz NOT NULL DEFAULT now(),
    expires_at   date NOT NULL,
    note         text NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS certificate_ops (
    id             bigserial PRIMARY KEY,
    certificate_id int NOT NULL REFERENCES certificates(id),
    kind           text NOT NULL CHECK (kind IN ('sale', 'redeem', 'refund', 'cancel')),
    amount         int NOT NULL,
    booking_id     int REFERENCES bookings(id),
    actor          text NOT NULL DEFAULT '',
    note           text NOT NULL DEFAULT '',
    created_at     timestamptz NOT NULL DEFAULT now()
);

-- Сотрудники и доступ к рабочему кабинету.
CREATE TABLE IF NOT EXISTS employees (
    id         serial PRIMARY KEY,
    name       text NOT NULL,
    phone      text,
    position   text NOT NULL CHECK (position IN ('manager', 'admin', 'master', 'cleaning')),
    master_id  int REFERENCES masters(id),
    login      text UNIQUE,
    pin_hash   text,
    active     boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now()
);

-- Сегменты (ручные метки гостей, которые ставят автоматизации и рассылки).
CREATE TABLE IF NOT EXISTS guest_segments (
    guest_id int NOT NULL REFERENCES guests(id) ON DELETE CASCADE,
    segment  text NOT NULL,
    added_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (guest_id, segment)
);

-- Автоматизации маркетинга: событие → условия → действие.
CREATE TABLE IF NOT EXISTS automations (
    id           serial PRIMARY KEY,
    name         text NOT NULL,
    trigger      text NOT NULL CHECK (trigger IN ('birthday_before', 'after_visit', 'inactive', 'registration')),
    days         int NOT NULL DEFAULT 0,
    filters      jsonb NOT NULL DEFAULT '[]'::jsonb,
    action       text NOT NULL CHECK (action IN ('bonus', 'message', 'segment_add', 'segment_remove')),
    bonus_amount int NOT NULL DEFAULT 0,
    bonus_days   int NOT NULL DEFAULT 14,
    message      text NOT NULL DEFAULT '',
    segment      text NOT NULL DEFAULT '',
    active       boolean NOT NULL DEFAULT true,
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS automation_runs (
    automation_id int NOT NULL REFERENCES automations(id) ON DELETE CASCADE,
    guest_id      int NOT NULL REFERENCES guests(id) ON DELETE CASCADE,
    run_key       text NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (automation_id, guest_id, run_key)
);

-- Рассылки: фильтры, кнопки, отложенная отправка.
ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS filters jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS buttons jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS scheduled_at timestamptz;
ALTER TABLE campaigns DROP CONSTRAINT IF EXISTS campaigns_status_check;
ALTER TABLE campaigns ADD CONSTRAINT campaigns_status_check CHECK (status IN ('draft', 'scheduled', 'sent'));
