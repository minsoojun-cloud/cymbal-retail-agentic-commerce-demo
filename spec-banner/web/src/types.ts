export type CategoryId =
  | 'tv'
  | 'pc'
  | 'wine_cellar'
  | 'cooler_warmer'
  | 'freezer'
  | 'refrigerator';

export interface CategoryField {
  key: string;
  label: string;
  group: string;
  type: 'text' | 'number' | 'select';
  unit?: string | null;
  choices?: string[] | null;
  default?: any;
}

export interface CategoryDefinition {
  id: CategoryId;
  name: string;
  en_name: string;
  icon: string;
  orientation: 'landscape' | 'portrait';
  aspect_ratio: string;
  excel_sheet_name: string;
  specimen_image: string;
  description: string;
  fields: CategoryField[];
  count: number;
}

export interface ProductItem {
  id: number;
  kinohyo_id: number | null;
  product_id: number | null;
  jan_code: string;
  search_model_no: string;
  maker_model_no: string;
  maker_code: string;
  maker_name: string;
  product_name: string;
  class_code: string;
  category: CategoryId;
  category_name: string;
  template_variant: string;
  has_kinohyo: boolean;
  linked_master: boolean;
  edion_price: number;
  shikiri_price: number;
  margin_rate: number;
  maker_price: string;
  long_warranty: string;
  features: string;
  rec_comment_1: string;
  rec_comment_2: string;
  rec_comment_3: string;
  effective_date: string;
  specs: Record<string, any>;
  ai_metadata: {
    summary?: string;
    sources?: Array<{ title: string; uri: string }>;
    updated_keys?: string[];
    model?: string;
    at?: string;
  };
  updated_at: string | null;
  registration_url: string;
}

export interface EmailLogItem {
  id: number;
  product_id: number | null;
  jan_code: string | null;
  search_model_no: string | null;
  category: string | null;
  to_email: string;
  cc_email: string | null;
  subject: string;
  attachment_format: string;
  status: string;
  delivery_method: string;
  jpeg_uri: string | null;
  pdf_uri: string | null;
  meta: Record<string, any>;
  created_at: string | null;
  sent_at: string | null;
}

export const DOOR_IMAGE_MAP: Record<string, string> = {
  扉1枚A: '/assets/doors/door_1a.png',
  扉1枚B: '/assets/doors/door_1b.png',
  扉2枚A: '/assets/doors/door_2a.png',
  扉2枚B: '/assets/doors/door_2b.png',
  扉2枚C: '/assets/doors/door_2c.png',
  扉2枚D: '/assets/doors/door_2d.png',
  扉3枚: '/assets/doors/door_3.png',
  扉4枚: '/assets/doors/door_4.png',
  扉4枚2室: '/assets/doors/door_4_2.png',
  扉5枚A: '/assets/doors/door_5a.png',
  扉5枚B: '/assets/doors/door_5b.png',
  扉5枚C: '/assets/doors/door_5c.png',
};

export type WidgetBoxType =
  | 'header_banner'
  | 'kv_card'
  | 'hero_metric'
  | 'boolean_badge'
  | 'spec_table'
  | 'vod_grid'
  | 'energy_label_unified'
  | 'energy_label_tv'
  | 'door_diagram_3d'
  | 'door_swing_svg'
  | 'e_angle_select'
  | 'recycling_footer'
  | 'jan_barcode'
  | 'dimension_diagram'
  | 'point_callout'
  | 'static_banner';

export interface FieldBinding {
  field_key: string;
  label_override?: string | null;
  unit_override?: string | null;
  prefix_text?: string | null;
  sub_field_keys?: string[];
  empty_fallback?: string;
}

export interface LayoutBox {
  id: string;
  box_type: WidgetBoxType;
  title: string;
  show_title_bar: boolean;
  title_bg_color: string;
  title_text_color: string;
  bg_color: string;
  border_color: string;
  border_width: number;
  border_radius: number;
  x: number;
  y: number;
  w: number;
  h: number;
  value_font_size: number | 'auto';
  value_color: string;
  text_align: 'left' | 'center' | 'right';
  binding: FieldBinding;
}

export interface HeaderConfig {
  visible: boolean;
  height: number;
  default_bg_color: string;
  text_color: string;
  main_title_mode: 'field' | 'static';
  main_title_field_key: string;
  main_title_static: string;
  top_right_1_field_key: string;
  top_right_2_field_key: string;
  bottom_right_field_key: string;
  sub_left_field_key: string;
}

export interface TemplateSchema {
  template_id: string;
  name: string;
  category: CategoryId;
  orientation: 'landscape' | 'portrait';
  is_preset?: boolean;
  status?: 'draft' | 'published';
  is_category_default?: boolean;
  assigned_models?: string[];
  canvas_width: number;
  canvas_height: number;
  canvas_bg_color: string;
  outer_padding: number;
  grid_snap_px: number;
  header: HeaderConfig;
  boxes: LayoutBox[];
  custom_fields?: CategoryField[];
  source_image_data_url?: string;
  updated_at?: string;
}
