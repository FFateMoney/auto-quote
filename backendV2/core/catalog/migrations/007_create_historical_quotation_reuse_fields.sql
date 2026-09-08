CREATE TABLE IF NOT EXISTS public.historical_quotation_reuse_fields (
    id smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    field_name text NOT NULL UNIQUE,
    field_section text NOT NULL CHECK (field_section IN ('fixed_fields', 'special_fields')),
    cache_scope text NOT NULL,
    is_grouping_key boolean NOT NULL DEFAULT FALSE,
    description text NOT NULL
);

INSERT INTO public.historical_quotation_reuse_fields (
    field_name, field_section, cache_scope, is_grouping_key, description
) VALUES
    ('standard_document_section', 'fixed_fields', 'standard_clause', TRUE, '标准文档章节'),
    ('temperature_min_c', 'special_fields', 'standard_clause', FALSE, '最低温度'),
    ('temperature_max_c', 'special_fields', 'standard_clause', FALSE, '最高温度'),
    ('humidity_min_rh', 'special_fields', 'standard_clause', FALSE, '最低湿度'),
    ('humidity_max_rh', 'special_fields', 'standard_clause', FALSE, '最高湿度'),
    ('max_temperature_change_rate_c_per_min', 'special_fields', 'standard_clause', FALSE, '最大温度变化速率'),
    ('water_temperature_min_c', 'special_fields', 'standard_clause', FALSE, '最低水温'),
    ('water_temperature_max_c', 'special_fields', 'standard_clause', FALSE, '最高水温'),
    ('water_flow_min_l_per_min', 'special_fields', 'standard_clause', FALSE, '最低水流量'),
    ('water_flow_max_l_per_min', 'special_fields', 'standard_clause', FALSE, '最高水流量'),
    ('irradiance_min_w_per_m3', 'special_fields', 'standard_clause', FALSE, '最低辐照量'),
    ('irradiance_max_w_per_m3', 'special_fields', 'standard_clause', FALSE, '最高辐照量'),
    ('frequency_min_hz', 'special_fields', 'standard_clause', FALSE, '最低频率'),
    ('frequency_max_hz', 'special_fields', 'standard_clause', FALSE, '最高频率'),
    ('acceleration_min_m_per_s2', 'special_fields', 'standard_clause', FALSE, '最低加速度'),
    ('acceleration_max_m_per_s2', 'special_fields', 'standard_clause', FALSE, '最高加速度'),
    ('max_peak_to_peak_displacement_mm', 'special_fields', 'standard_clause', FALSE, '最大峰峰位移')
ON CONFLICT (field_name) DO UPDATE SET
    field_section = EXCLUDED.field_section,
    cache_scope = EXCLUDED.cache_scope,
    is_grouping_key = EXCLUDED.is_grouping_key,
    description = EXCLUDED.description;
