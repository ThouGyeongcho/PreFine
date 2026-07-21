export interface CurrentUser {
  username: string;
}

export interface HealthStatus {
  status: string;
  database: string;
  scheduler: string;
  version: string;
}

export interface Region {
  code: string;
  name: string;
  region_code: string;
}

export interface OfficialCalendarEvent {
  source_event_id: string;
  start_date: string;
  end_date: string;
  bssz: string;
  split_items: string[];
  source_agency: string | null;
  source_created_at: string | null;
  source_order: number;
}

export interface PersonalizedCalendarEvent {
  key: string;
  source_event_id: string;
  category: string;
  item_code: string | null;
  display_name: string;
  official_text: string;
  matched_text: string;
  start_date: string;
  end_date: string;
  source_order: number;
  needs_confirmation: boolean;
}

export interface CalendarMonth {
  region_code: string;
  month: string;
  official_events: OfficialCalendarEvent[];
  personalized_events: PersonalizedCalendarEvent[];
  profile_complete: boolean;
  stale: boolean;
  sync_status: string;
  last_succeeded_at: string | null;
  source_url: string;
}

export type TaxpayerType = "general_taxpayer" | "small_scale_taxpayer";
export type CalendarMode = "official" | "personalized";

export interface TaxToolSettings {
  default_mode: CalendarMode;
  taxpayer_type: TaxpayerType | null;
  selected_item_codes: string[];
  default_region_code: string | null;
  reminder_days: number[];
  profile_complete: boolean;
  email_configured: boolean;
}

export interface TaxCatalogItem {
  code: string;
  category: string;
  display_name: string;
  taxpayer_scope: TaxpayerType[];
}
