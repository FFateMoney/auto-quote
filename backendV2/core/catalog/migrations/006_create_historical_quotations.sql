CREATE TABLE IF NOT EXISTS public.historical_quotations (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    quotation_run_id text NOT NULL,
    quote_id text NOT NULL,
    source_snapshot_id text,
    source_file_name text NOT NULL,
    raw_test_type text,
    test_project_id bigint,
    standard_type text,
    test_item text,
    standard_code text,
    standard_document_section text,
    pricing_mode text,
    specification text,
    pricing_quantity numeric(14, 3),
    sample_count numeric(14, 3),
    length_mm numeric(14, 3),
    width_mm numeric(14, 3),
    height_mm numeric(14, 3),
    special_fields jsonb NOT NULL DEFAULT '{}'::jsonb,
    base_fee numeric(12, 2),
    unit_price numeric(12, 2),
    total_price numeric(12, 2),
    selected_device_code text,
    quotation_snapshot jsonb NOT NULL,
    saved_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (quotation_run_id, quote_id)
);

CREATE INDEX IF NOT EXISTS historical_quotations_saved_at_index
    ON public.historical_quotations (saved_at DESC);

CREATE INDEX IF NOT EXISTS historical_quotations_project_index
    ON public.historical_quotations (standard_type, test_item, standard_code);
