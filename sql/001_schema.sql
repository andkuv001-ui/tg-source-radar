-- ============================================================
-- TG Source Radar — Database Schema (Chat Discovery)
-- Uses public schema (default for Supabase service_role)
-- Run in Supabase SQL Editor
-- ============================================================

-- 0. Extensions
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Tables

CREATE TABLE IF NOT EXISTS public.search_queries (
  id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  topic         TEXT NOT NULL,
  keywords      TEXT[] NOT NULL DEFAULT '{}',
  status        TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'searching', 'evaluating', 'completed', 'failed')),
  total_found   INTEGER DEFAULT 0,
  total_scored  INTEGER DEFAULT 0,
  error_message TEXT,
  created_at    TIMESTAMPTZ DEFAULT now(),
  completed_at  TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS public.found_chats (
  id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  telegram_chat_id  BIGINT NOT NULL UNIQUE,
  title             TEXT,
  username          TEXT,
  description       TEXT,
  participants_count INTEGER,
  is_channel        BOOLEAN DEFAULT false,
  is_megagroup      BOOLEAN DEFAULT false,
  photo_url         TEXT,
  raw_data          JSONB DEFAULT '{}',
  first_seen_at     TIMESTAMPTZ DEFAULT now(),
  updated_at        TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.chat_evaluations (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  query_id        UUID NOT NULL REFERENCES public.search_queries(id) ON DELETE CASCADE,
  chat_id         UUID NOT NULL REFERENCES public.found_chats(id) ON DELETE CASCADE,
  relevance_score NUMERIC(3,2) NOT NULL DEFAULT 0.00,
  topic_match     TEXT,
  category        TEXT,
  language        TEXT DEFAULT 'ru',
  channel_type    TEXT,
  is_community    BOOLEAN DEFAULT false,
  llm_raw_response JSONB DEFAULT '{}',
  created_at      TIMESTAMPTZ DEFAULT now(),
  UNIQUE(query_id, chat_id)
);

-- 2. Indexes

CREATE INDEX IF NOT EXISTS idx_queries_status ON public.search_queries(status)
  WHERE status IN ('pending', 'searching', 'evaluating');

CREATE INDEX IF NOT EXISTS idx_chats_username ON public.found_chats(username)
  WHERE username IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_chats_title_trgm ON public.found_chats USING GIN(title gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_chats_desc_trgm ON public.found_chats USING GIN(description gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_eval_query_score ON public.chat_evaluations(query_id, relevance_score DESC);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public'
    AND table_name = 'found_chats'
    AND column_name = 'description_vector'
  ) THEN
    ALTER TABLE public.found_chats ADD COLUMN description_vector TSVECTOR
      GENERATED ALWAYS AS (to_tsvector('russian', COALESCE(description, ''))) STORED;
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_chats_desc_fts ON public.found_chats USING GIN(description_vector);

CREATE INDEX IF NOT EXISTS idx_chats_participants ON public.found_chats(participants_count DESC NULLS LAST);

-- 3. Triggers

CREATE OR REPLACE FUNCTION public.update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_chats_updated_at ON public.found_chats;
CREATE TRIGGER trg_chats_updated_at
  BEFORE UPDATE ON public.found_chats
  FOR EACH ROW
  EXECUTE FUNCTION public.update_timestamp();

-- 4. View

CREATE OR REPLACE VIEW public.search_results AS
SELECT
  sq.id AS query_id,
  sq.topic,
  sq.keywords,
  sq.status AS query_status,
  sq.created_at AS searched_at,
  fc.id AS chat_id,
  fc.telegram_chat_id,
  fc.title AS chat_title,
  fc.username AS chat_username,
  fc.description AS chat_description,
  fc.participants_count,
  fc.is_channel,
  ce.relevance_score,
  ce.topic_match,
  ce.category,
  ce.channel_type,
  ce.is_community,
  'https://t.me/' || COALESCE(fc.username, 'c/' || ABS(fc.telegram_chat_id)) AS telegram_link
FROM public.search_queries sq
JOIN public.chat_evaluations ce ON ce.query_id = sq.id
JOIN public.found_chats fc ON fc.id = ce.chat_id
ORDER BY sq.created_at DESC, ce.relevance_score DESC;

-- 5. Migration for existing databases (safe to re-run)
ALTER TABLE public.chat_evaluations ADD COLUMN IF NOT EXISTS channel_type TEXT;
ALTER TABLE public.chat_evaluations ADD COLUMN IF NOT EXISTS is_community BOOLEAN DEFAULT false;
