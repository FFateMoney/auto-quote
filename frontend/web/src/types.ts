export type ManualOverride = {
  field_name: string;
  value: unknown;
  updated_at: string;
};

export type EquipmentRejection = {
  equipment_id: string;
  equipment_label: string;
  reasons: string[];
  missing_fields: string[];
};

export type EquipmentProfile = {
  equipment_id: string;
  equipment_label: string;
  attributes: Record<string, unknown>;
};

export type ExtraStandardRequirement = {
  requirement_name: string;
  requirement_text: string;
  source_section: string;
};

export type FormRow = {
  row_id: string;
  raw_test_type: string;
  canonical_test_type: string;
  standard_codes: string[];
  pricing_mode: string;
  pricing_quantity: number | null;
  sample_count: number | null;
  repeat_count: number | null;
  sample_length_mm: number | null;
  sample_width_mm: number | null;
  sample_height_mm: number | null;
  sample_weight_kg: number | null;
  required_temp_min: number | null;
  required_temp_max: number | null;
  required_humidity_min: number | null;
  required_humidity_max: number | null;
  required_temp_change_rate: number | null;
  required_freq_min: number | null;
  required_freq_max: number | null;
  required_accel_min: number | null;
  required_accel_max: number | null;
  required_displacement_min: number | null;
  required_displacement_max: number | null;
  required_irradiance_min: number | null;
  required_irradiance_max: number | null;
  required_water_temp_min: number | null;
  required_water_temp_max: number | null;
  required_water_flow_min: number | null;
  required_water_flow_max: number | null;
  planned_standard_fields: string[];
  discovered_standard_fields: string[];
  extra_standard_requirements: ExtraStandardRequirement[];
  source_text: string;
  conditions_text: string;
  sample_info_text: string;
  stage_status: string;
  missing_fields: string[];
  blocking_reason: string;
  matched_test_type_id: number | null;
  candidate_equipment_ids: string[];
  candidate_equipment_profiles: EquipmentProfile[];
  selected_equipment_id: string;
  rejected_equipment: EquipmentRejection[];
  base_fee: number | null;
  unit_price: number | null;
  total_price: number | null;
  formula: string;
  price_unit: string;
  manual_overrides: Record<string, ManualOverride>;
};

export type FormStageSnapshot = {
  stage_id: string;
  label: string;
  items: FormRow[];
  notes: string[];
  created_at: string;
};

export type UploadedDocument = {
  document_id: string;
  file_name: string;
  media_type: string;
  stored_path: string;
  source_kind: string;
  status: string;
  notes: string;
};

export type RunArtifacts = {
  run_state_path: string;
  uploaded_dir: string;
  exported_files: string[];
};

export type RunState = {
  run_id: string;
  current_stage: string;
  overall_status: "running" | "waiting_manual_input" | "completed" | "failed";
  uploaded_documents: UploadedDocument[];
  form_stages: FormStageSnapshot[];
  final_form_items: FormRow[];
  next_action: string;
  artifacts: RunArtifacts;
  errors: string[];
  created_at: string;
  updated_at: string;
};

export type TestTypeOption = {
  id: number;
  name: string;
  aliases: string[];
  pricing_mode: string;
};

export type TestTypeCatalogResponse = {
  items: TestTypeOption[];
  load_error: string;
};
