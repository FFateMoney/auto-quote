ALTER TABLE public.test_projects
    ADD COLUMN IF NOT EXISTS is_deleted boolean NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS test_projects_active_index
    ON public.test_projects (standard_type, test_item, max_specification)
    WHERE is_deleted = FALSE;
