export interface BrandingConfig {
  agency_name: string;
  tagline: string;
  logo_url: string;
  primary_color: string;
  gold_color: string;
  navy_color: string;
  accent_red: string;
  contact_email: string;
  whatsapp_number: string;
  website_url: string;
  compliance_notice: string;
}

export interface UserAccount {
  id: number;
  email: string;
  full_name: string;
  role: "ceo" | "staff" | "customer";
  linked_case_id: string | null;
  is_active: boolean;
  created_at?: string;
}

export interface RiskFlag {
  id: number;
  code: string;
  severity: "red" | "amber" | "green";
  category: string;
  title: string;
  detail: string;
  suggested_fix: string;
  follow_up_question: string;
  client_response: string;
  options?: string[];
  source_citation: string;
  source_url: string;
  score_impact: number;
  resolved: boolean;
}

export interface InterviewPrediction {
  id: number;
  theme_id: string;
  question_text: string;
  question_type: "profile_driven" | "policy_mandatory";
  rank: number;
  confidence: number;
  rationale: string;
  author: string;
  frozen_at: string | null;
}

export interface GeneratedAsset {
  id: number;
  asset_type: string;
  title: string;
  filename: string;
  mime_type: string;
  approval_status: "pending_approval" | "approved" | "rejected";
  approved_by: string;
  approved_at: string | null;
  visible_to_client: boolean;
  created_at: string | null;
}

export interface JournalEntry {
  id: number;
  event_type: string;
  actor: string;
  summary: string;
  metadata?: Record<string, unknown>;
  created_at: string | null;
}

export interface ProfileFact {
  id: number;
  fact_key: string;
  value: string;
  as_of_date: string;
  evidence_source: string;
  confidence: string;
  conflict_status: string;
  resolution_note: string;
}

export interface InterviewEventItem {
  id: number;
  event_mode: string;
  sequence: number;
  theme: string;
  question_text: string;
  client_answer: string;
  discrepancy_type: string;
  verified_resolution: string;
  source_type: string;
  pre_interview_predicted_theme: boolean;
  prediction_classification: string;
  created_at: string | null;
}

export interface ClientSummary {
  case_id: string;
  access_code: string;
  pseudonym: string;
  full_name: string;
  email: string;
  phone: string;
  nationality: string;
  parish: string;
  visa_class: string;
  pipeline_stage: string;
  standing_score: number;
  denial_risk_level: string;
  outcome: string;
  outcome_evidence: string;
  prior_us_refusals: number;
  embassy_interview_date: string;
  assigned_staff: string;
  predictions_frozen: boolean;
  profile_tags: string[];
  service_package_usd: number;
  updated_at: string | null;
}

export interface ClientDetail extends ClientSummary {
  passport_number: string;
  dob: string;
  passport_expiry: string;
  ds160_confirmation_id: string;
  ais_appointment_barcode: string;
  intended_travel_date: string;
  intended_return_date: string;
  purpose_of_trip: string;
  us_destination: string;
  us_host_contact: string;
  occupation: string;
  employer_name: string;
  monthly_gross_jmd: number | null;
  monthly_net_jmd: number | null;
  marital_status: string;
  children_count: number;
  has_us_relatives: boolean;
  us_relatives_details: string;
  travel_history_summary: string;
  refusal_statute: string;
  predictions_frozen_at: string | null;
  predictions_frozen_by: string;
  data_quality: string;
  open_verification_items: string;
  consent_status: string;
  risk_flags: RiskFlag[];
  predictions: InterviewPrediction[];
  assets: GeneratedAsset[];
  facts?: ProfileFact[];
  interview_events?: InterviewEventItem[];
  journal?: JournalEntry[];
}

export interface GovSourceItem {
  id: number;
  source_key: string;
  name: string;
  agency: string;
  category: string;
  url: string;
  verified_summary: string;
  scraped_excerpt: string;
  key_rules: string[];
  content_hash: string;
  diff_alert: boolean;
  diff_summary: string;
  scrape_status: string;
  last_scraped_at: string | null;
  enabled: boolean;
}

export interface OfficialDocItem {
  id: number;
  doc_key: string;
  title: string;
  agency: string;
  category: string;
  filename: string;
  file_format: string;
  size_bytes: number;
  sha256: string;
  source_url: string;
  description: string;
  detected_fields: string[];
  is_blueprint: boolean;
  file_exists: boolean;
  view_url: string;
}

export interface VaultNoteMeta {
  path: string;
  name: string;
  folder: string;
  size_bytes: number;
  updated_at: string;
  links: string[];
  tags: string[];
  excerpt: string;
}

export interface QuestionnaireItem {
  flag_id: number;
  code: string;
  title: string;
  question: string;
  explanation: string;
  tip: string;
  options: string[];
  client_response: string;
  resolved: boolean;
  severity: string;
  source_citation?: string;
}

export interface ChatQuestionnairePayload {
  case_id: string;
  client_name: string;
  visa_class: string;
  standing_score: number;
  total_count: number;
  answered_count: number;
  items: QuestionnaireItem[];
}
