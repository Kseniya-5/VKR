ALTER TABLE password_reset_tokens
    ADD COLUMN IF NOT EXISTS telegram_chat_id BIGINT,
    ADD COLUMN IF NOT EXISTS telegram_message_id INTEGER,
    ADD COLUMN IF NOT EXISTS telegram_message_deleted_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_telegram_message
    ON password_reset_tokens (telegram_chat_id, telegram_message_id);
