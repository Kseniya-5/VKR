-- 1. Главная таблица пользователей
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    is_deleted BOOLEAN DEFAULT FALSE, -- Мягкое удаление
    deleted_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. Telegram-аккаунты 
CREATE TABLE IF NOT EXISTS telegram_accounts (
    telegram_id BIGINT PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    username VARCHAR(255),
    first_name VARCHAR(255),
    last_name VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id) -- У одного пользователя может быть только один привязанный TG
);

-- 3. Web-аккаунты
CREATE TABLE IF NOT EXISTS web_accounts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id),
    CONSTRAINT valid_email CHECK (
        email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'
    )
);

-- 4. Одноразовые коды для связывания 
CREATE TABLE IF NOT EXISTS account_link_codes (
    code VARCHAR(10) PRIMARY KEY, 
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 5. Таблица задач 
CREATE TABLE IF NOT EXISTS model_tasks (
    task_id VARCHAR(255) PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status VARCHAR(50) NOT NULL,
    result TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 6. Фотографии пользователя
CREATE TABLE IF NOT EXISTS user_photos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    source VARCHAR(20) NOT NULL CHECK (source IN ('telegram', 'web')),
    telegram_file_id TEXT,
    telegram_file_unique_id TEXT,

    original_path TEXT,
    processed_path TEXT,
    preview_path TEXT,

    mime_type VARCHAR(100),
    file_size BIGINT,
    width INTEGER,
    height INTEGER,

    item_type VARCHAR(50),      
    category VARCHAR(100),      
    subcategory VARCHAR(100),   
    color VARCHAR(100),
    season VARCHAR(50),         
    style VARCHAR(100),        
    brand VARCHAR(255),

    tags TEXT,                  
    notes TEXT,

    is_favorite BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    processing_status VARCHAR(50) NOT NULL DEFAULT 'uploaded'
        CHECK (processing_status IN ('uploaded', 'processing', 'ready', 'failed')),

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user_photos_user_id ON user_photos(user_id);
CREATE INDEX IF NOT EXISTS idx_user_photos_item_type ON user_photos(item_type);
CREATE INDEX IF NOT EXISTS idx_user_photos_category ON user_photos(category);
CREATE INDEX IF NOT EXISTS idx_user_photos_processing_status ON user_photos(processing_status);


-- 7. Задачи обработки фото
CREATE TABLE IF NOT EXISTS photo_processing_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    photo_id UUID NOT NULL REFERENCES user_photos(id) ON DELETE CASCADE,
    task_id VARCHAR(255),  -- если используешь celery task id
    job_type VARCHAR(50) NOT NULL
        CHECK (job_type IN ('background_removal', 'classification', 'embedding', 'other')),
    status VARCHAR(50) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'processing', 'done', 'failed')),
    result_path TEXT,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_photo_processing_jobs_photo_id ON photo_processing_jobs(photo_id);
CREATE INDEX IF NOT EXISTS idx_photo_processing_jobs_status ON photo_processing_jobs(status);


-- 8. Собранные образы
CREATE TABLE IF NOT EXISTS outfits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,

    title VARCHAR(255),
    occasion VARCHAR(100),   
    season VARCHAR(50),      
    style VARCHAR(100),     
    description TEXT,

    generated_by VARCHAR(20) NOT NULL DEFAULT 'system'
        CHECK (generated_by IN ('user', 'system')),

    is_favorite BOOLEAN NOT NULL DEFAULT FALSE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_outfits_user_id ON outfits(user_id);
CREATE INDEX IF NOT EXISTS idx_outfits_occasion ON outfits(occasion);
CREATE INDEX IF NOT EXISTS idx_outfits_style ON outfits(style);


-- 9. Элементы образа
CREATE TABLE IF NOT EXISTS outfit_items (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    outfit_id UUID NOT NULL REFERENCES outfits(id) ON DELETE CASCADE,
    photo_id UUID NOT NULL REFERENCES user_photos(id) ON DELETE CASCADE,

    item_role VARCHAR(50) NOT NULL, 
    sort_order INTEGER NOT NULL DEFAULT 0,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT unique_outfit_photo UNIQUE (outfit_id, photo_id)
);

CREATE INDEX IF NOT EXISTS idx_outfit_items_outfit_id ON outfit_items(outfit_id);
CREATE INDEX IF NOT EXISTS idx_outfit_items_photo_id ON outfit_items(photo_id);


-- 10. Рекомендации
CREATE TABLE IF NOT EXISTS recommendations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    outfit_id UUID REFERENCES outfits(id) ON DELETE SET NULL,

    recommendation_type VARCHAR(50) NOT NULL
        CHECK (recommendation_type IN ('outfit', 'item', 'style_tip', 'color_match', 'seasonal')),

    title VARCHAR(255),
    description TEXT NOT NULL,

    source VARCHAR(20) NOT NULL DEFAULT 'system'
        CHECK (source IN ('system', 'ml', 'user')),

    status VARCHAR(50) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'archived', 'dismissed')),

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 11. Токены для восстановления пароля
CREATE TABLE IF NOT EXISTS password_reset_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash VARCHAR(255) NOT NULL,
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    used_at TIMESTAMP WITH TIME ZONE,
    telegram_chat_id BIGINT,
    telegram_message_id INTEGER,
    telegram_message_deleted_at TIMESTAMPTZ,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_user_id ON password_reset_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_telegram_message
    ON password_reset_tokens (telegram_chat_id, telegram_message_id);
CREATE INDEX IF NOT EXISTS idx_recommendations_user_id ON recommendations(user_id);
CREATE INDEX IF NOT EXISTS idx_recommendations_type ON recommendations(recommendation_type);
CREATE INDEX IF NOT EXISTS idx_recommendations_outfit_id ON recommendations(outfit_id);


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

ALTER TABLE password_reset_tokens
    ADD COLUMN IF NOT EXISTS telegram_chat_id BIGINT,
    ADD COLUMN IF NOT EXISTS telegram_message_id INTEGER,
    ADD COLUMN IF NOT EXISTS telegram_message_deleted_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_password_reset_tokens_telegram_message
    ON password_reset_tokens (telegram_chat_id, telegram_message_id);
