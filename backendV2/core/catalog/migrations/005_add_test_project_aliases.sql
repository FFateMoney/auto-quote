ALTER TABLE public.test_projects
    ADD COLUMN IF NOT EXISTS aliases text[] NOT NULL DEFAULT '{}';
