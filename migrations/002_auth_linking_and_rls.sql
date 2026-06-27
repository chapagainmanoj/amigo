-- Link Supabase Auth identity to application user
ALTER TABLE user_profiles
  ADD COLUMN supabase_auth_id UUID UNIQUE;

-- Pairing tokens for Telegram account linking
CREATE TABLE pairing_tokens (
    token TEXT PRIMARY KEY,
    supabase_auth_id UUID NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL,
    consumed BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_pairing_tokens_expiry
  ON pairing_tokens(expires_at) WHERE consumed = FALSE;

-- RLS policies (using the linked auth identity)
CREATE POLICY "Users see own profile"
  ON user_profiles FOR SELECT TO authenticated
  USING (supabase_auth_id = auth.uid());

CREATE POLICY "Users update own profile"
  ON user_profiles FOR UPDATE TO authenticated
  USING (supabase_auth_id = auth.uid())
  WITH CHECK (supabase_auth_id = auth.uid());

CREATE POLICY "Users see own tasks"
  ON tasks FOR ALL TO authenticated
  USING (user_id IN (
    SELECT user_id FROM user_profiles
    WHERE supabase_auth_id = auth.uid()
  ));

CREATE POLICY "Users see own reminders"
  ON reminders FOR ALL TO authenticated
  USING (user_id IN (
    SELECT user_id FROM user_profiles
    WHERE supabase_auth_id = auth.uid()
  ));

CREATE POLICY "Users see own sessions"
  ON sessions FOR SELECT TO authenticated
  USING (user_id IN (
    SELECT user_id FROM user_profiles
    WHERE supabase_auth_id = auth.uid()
  ));

CREATE POLICY "Users see own messages"
  ON messages FOR SELECT TO authenticated
  USING (user_id IN (
    SELECT user_id FROM user_profiles
    WHERE supabase_auth_id = auth.uid()
  ));
