BEGIN;

DROP TABLE IF EXISTS public.test_type_equipment CASCADE;
DROP TABLE IF EXISTS public.equipment_pricing CASCADE;
DROP TABLE IF EXISTS public.test_types CASCADE;
DROP TABLE IF EXISTS public.equipment CASCADE;
DROP TABLE IF EXISTS public.test_project_capability_sets CASCADE;
DROP TABLE IF EXISTS public.test_projects CASCADE;
DROP TABLE IF EXISTS public.device_capabilities CASCADE;

CREATE TABLE public.test_projects (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    standard_type text NOT NULL,
    test_item text NOT NULL,
    max_specification text NOT NULL,
    pricing_mode text NOT NULL,
    base_fee numeric(12, 2) NOT NULL,
    unit_price numeric(12, 2) NOT NULL,
    applicable_device_codes text[] NOT NULL,
    aliases text[] NOT NULL DEFAULT '{}',
    is_deleted boolean NOT NULL DEFAULT FALSE,
    UNIQUE (standard_type, test_item, max_specification)
);

CREATE TABLE public.device_capabilities (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    device_code text NOT NULL UNIQUE,
    max_volume_m3 numeric(12, 3),
    max_length_mm numeric(12, 3),
    max_width_mm numeric(12, 3),
    max_height_mm numeric(12, 3),
    temperature_min_c numeric(12, 3),
    temperature_max_c numeric(12, 3),
    humidity_min_rh numeric(12, 3),
    humidity_max_rh numeric(12, 3),
    max_temperature_change_rate_c_per_min numeric(12, 3),
    water_temperature_min_c numeric(12, 3),
    water_temperature_max_c numeric(12, 3),
    water_flow_min_l_per_min numeric(12, 3),
    water_flow_max_l_per_min numeric(12, 3),
    irradiance_min_w_per_m3 numeric(12, 3),
    irradiance_max_w_per_m3 numeric(12, 3),
    max_load_kg numeric(12, 3),
    other_limits text,
    frequency_min_hz numeric(12, 3),
    frequency_max_hz numeric(12, 3),
    acceleration_min_m_per_s2 numeric(12, 3),
    acceleration_max_m_per_s2 numeric(12, 3),
    max_peak_to_peak_displacement_mm numeric(12, 3),
    power_kwh numeric(12, 3),
    is_deleted boolean NOT NULL DEFAULT FALSE
);

CREATE TABLE public.test_project_capability_sets (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    test_project_id bigint NOT NULL UNIQUE REFERENCES public.test_projects (id) ON DELETE CASCADE,
    capability_fields text[] NOT NULL
);

COMMIT;
