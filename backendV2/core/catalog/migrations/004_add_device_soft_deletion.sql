ALTER TABLE public.device_capabilities
    ADD COLUMN IF NOT EXISTS is_deleted boolean NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS device_capabilities_active_index
    ON public.device_capabilities (device_code)
    WHERE is_deleted = FALSE;
