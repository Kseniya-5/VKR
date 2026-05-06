ALTER TABLE users
    ADD COLUMN IF NOT EXISTS first_name VARCHAR(255),
    ADD COLUMN IF NOT EXISTS last_name VARCHAR(255);

UPDATE users u
SET
    first_name = COALESCE(u.first_name, ta.first_name),
    last_name = COALESCE(u.last_name, ta.last_name),
    updated_at = CURRENT_TIMESTAMP
FROM telegram_accounts ta
WHERE ta.user_id = u.id
  AND (u.first_name IS NULL OR u.last_name IS NULL);
