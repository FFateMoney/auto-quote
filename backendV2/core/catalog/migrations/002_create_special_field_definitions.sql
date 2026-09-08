CREATE TABLE IF NOT EXISTS public.special_field_definitions (
    id smallint PRIMARY KEY,
    field_name text NOT NULL UNIQUE,
    comparison_type_id smallint NOT NULL,
    comparison_type_description text NOT NULL
);

INSERT INTO public.special_field_definitions (
    id, field_name, comparison_type_id, comparison_type_description
) VALUES
    (1, 'temperature_min_c', 0, '设备最低温度小于等于需求最低温度'),
    (2, 'temperature_max_c', 1, '设备最高温度大于等于需求最高温度'),
    (3, 'humidity_min_rh', 0, '设备最低湿度小于等于需求最低湿度'),
    (4, 'humidity_max_rh', 1, '设备最高湿度大于等于需求最高湿度'),
    (5, 'max_temperature_change_rate_c_per_min', 1, '设备最大温度变化速率大于等于需求值'),
    (6, 'water_temperature_min_c', 0, '设备最低水温小于等于需求最低水温'),
    (7, 'water_temperature_max_c', 1, '设备最高水温大于等于需求最高水温'),
    (8, 'water_flow_min_l_per_min', 0, '设备最低水流量小于等于需求最低水流量'),
    (9, 'water_flow_max_l_per_min', 1, '设备最高水流量大于等于需求最高水流量'),
    (10, 'irradiance_min_w_per_m3', 0, '设备最低辐照量小于等于需求最低辐照量'),
    (11, 'irradiance_max_w_per_m3', 1, '设备最高辐照量大于等于需求最高辐照量'),
    (12, 'max_load_kg', 1, '设备最大负荷大于等于需求重量'),
    (13, 'frequency_min_hz', 0, '设备最低频率小于等于需求最低频率'),
    (14, 'frequency_max_hz', 1, '设备最高频率大于等于需求最高频率'),
    (15, 'acceleration_min_m_per_s2', 0, '设备最低加速度小于等于需求最低加速度'),
    (16, 'acceleration_max_m_per_s2', 1, '设备最高加速度大于等于需求最高加速度'),
    (17, 'max_peak_to_peak_displacement_mm', 1, '设备最大峰峰位移大于等于需求值')
ON CONFLICT (field_name) DO UPDATE SET
    comparison_type_id = EXCLUDED.comparison_type_id,
    comparison_type_description = EXCLUDED.comparison_type_description;
