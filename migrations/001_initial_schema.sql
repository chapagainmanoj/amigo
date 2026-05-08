-- Amigo Phase 1a Schema
-- Tenant-aware from day one (user_id + RLS on all tables)

CREATE TYPE task_category AS ENUM ('health', 'work', 'personal', 'social', 'other');
CREATE TYPE task_status AS ENUM ('pending', 'done', 'skipped', 'deferred');

CREATE TABLE user_profiles (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_chat_id BIGINT UNIQUE NOT NULL,
    name TEXT,
    timezone TEXT,
    wake_time TIME DEFAULT '07:30',
    sleep_time TIME DEFAULT '23:00',
    session_timeout_minutes INT DEFAULT 120,
    daily_message_budget INT DEFAULT 4,
    preferences JSONB DEFAULT '{}',
    coaching_profile JSONB DEFAULT '{"warmth":0.7,"directiveness":0.4,"challenge":0.4,"verbosity":0.5,"emotional_depth":0.5}',
    onboarding_complete BOOLEAN DEFAULT FALSE,
    onboarding_step INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE sessions (
    session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES user_profiles(user_id),
    session_type TEXT,
    started_at TIMESTAMPTZ DEFAULT now(),
    ended_at TIMESTAMPTZ,
    last_activity_at TIMESTAMPTZ DEFAULT now(),
    context_summary TEXT,
    message_count INT DEFAULT 0
);

CREATE TABLE tasks (
    task_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES user_profiles(user_id),
    title TEXT NOT NULL,
    category task_category DEFAULT 'other',
    due_date DATE,
    suggested_time TIMESTAMPTZ,
    actual_completion TIMESTAMPTZ,
    status task_status DEFAULT 'pending',
    deferred_count INT DEFAULT 0,
    source_session_id UUID REFERENCES sessions(session_id),
    created_date DATE DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE reminders (
    reminder_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id UUID REFERENCES tasks(task_id),
    user_id UUID REFERENCES user_profiles(user_id),
    scheduled_time TIMESTAMPTZ NOT NULL,
    status TEXT DEFAULT 'pending',
    snooze_count INT DEFAULT 0,
    telegram_message_id BIGINT,
    follow_up_sent BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE messages (
    message_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES sessions(session_id),
    user_id UUID REFERENCES user_profiles(user_id),
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    channel TEXT DEFAULT 'telegram',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE feedback (
    feedback_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES user_profiles(user_id),
    session_id UUID REFERENCES sessions(session_id),
    content TEXT NOT NULL,
    reviewed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE usage_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES user_profiles(user_id),
    model TEXT NOT NULL,
    input_tokens INT,
    output_tokens INT,
    estimated_cost NUMERIC(10,6),
    session_id UUID REFERENCES sessions(session_id),
    created_at TIMESTAMPTZ DEFAULT now()
);

-- RLS policies (tenant isolation)
ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE reminders ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_events ENABLE ROW LEVEL SECURITY;

-- Indexes for common queries
CREATE INDEX idx_tasks_user_date ON tasks(user_id, created_date);
CREATE INDEX idx_tasks_user_status ON tasks(user_id, status);
CREATE INDEX idx_sessions_user_active ON sessions(user_id, ended_at) WHERE ended_at IS NULL;
CREATE INDEX idx_sessions_last_activity ON sessions(last_activity_at);
CREATE INDEX idx_messages_session ON messages(session_id, created_at);
CREATE INDEX idx_reminders_scheduled ON reminders(scheduled_time, status) WHERE status = 'pending';
