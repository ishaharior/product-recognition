/**
 * Shared API types — mirrors the backend Pydantic schemas in
 * backend/app/schemas/__init__.py. Keep both sides in sync.
 */

export type VerificationStatus =
  | 'VERIFIED'
  | 'REVIEW_REQUIRED'
  | 'UNKNOWN_PRODUCT'
  | 'WEIGHT_MISMATCH'
  | 'COLOUR_MISMATCH'
  | 'SENSOR_UNAVAILABLE'
  | 'INSUFFICIENT_EVIDENCE';

export type InferenceMode = 'baseline' | 'custom' | 'demo';
export type WeightSource = 'real' | 'simulated' | 'none';

export interface HealthResponse {
  status: 'ok' | 'degraded';
  service: string;
  version: string;
  time: string;
}

export interface ModelStatus {
  mode: InferenceMode;
  available: boolean;
  model_name: string;
  weights_path: string;
  weights_present: boolean;
  classes: string[];
  class_count: number;
  message: string;
  is_generic_detector: boolean;
}

export interface SensorStatus {
  backend: 'mock' | 'serial' | 'disabled';
  connected: boolean;
  calibrated: boolean;
  simulated: boolean;
  port: string | null;
  last_reading_g: number | null;
  stable: boolean;
  message: string;
}

export interface DatasetStatus {
  config_path: string;
  config_exists: boolean;
  datasets_dir: string;
  prepared_datasets: string[];
  message: string;
}

export interface DemoStatus {
  active: boolean;
  paused: boolean;
  tick_ms: number;
  events_total: number;
  message: string;
}

export interface StatusResponse {
  inference: ModelStatus;
  sensor: SensorStatus;
  demo: DemoStatus;
  dataset: DatasetStatus;
  camera_expected: boolean;
  fps_limit: number;
  frame_max_size: number[];
}

export interface ColourVariant {
  id?: string;
  product_id?: string;
  colour_name: string;
  hex_value: string;
  primary_variant: boolean;
}

export interface Product {
  id: string;
  sku: string;
  name: string;
  category: string;
  description: string;
  reference_image: string;
  expected_gross_weight_g: number | null;
  expected_net_weight_g: number | null;
  packaging_weight_g: number | null;
  weight_tolerance_pct: number;
  weight_spec_kind: 'gross' | 'net';
  model_class_names: string;
  active: boolean;
  created_at: string;
  updated_at: string;
  colour_variants: ColourVariant[];
}

export interface ProductPayload {
  sku: string;
  name: string;
  category?: string;
  description?: string;
  reference_image?: string;
  expected_gross_weight_g?: number | null;
  expected_net_weight_g?: number | null;
  packaging_weight_g?: number | null;
  weight_tolerance_pct?: number;
  weight_spec_kind?: 'gross' | 'net';
  model_class_names?: string;
  active?: boolean;
  colour_variants?: { colour_name: string; hex_value: string; primary_variant: boolean }[];
}

export interface ProductListResponse {
  items: Product[];
  total: number;
}

export interface Scan {
  scan_id: string;
  timestamp: string;
  product_id: string | null;
  product_name: string | null;
  product_sku: string | null;
  detected_label: string;
  confidence: number;
  estimated_colour: string | null;
  colour_quality: string;
  colour_distribution: Record<string, number>;
  measured_weight_g: number | null;
  weight_unit: string;
  weight_source: WeightSource;
  weight_stable: boolean;
  expected_weight_g: number | null;
  weight_delta_pct: number | null;
  verification_status: VerificationStatus;
  verification_explanation: string;
  warnings: string[];
  inference_mode: InferenceMode;
  source: 'live' | 'demo';
  image_ref: string;
  inference_ms: number;
}

export interface ScanListResponse {
  items: Scan[];
  total: number;
  limit: number;
  offset: number;
}

export interface StatusCount {
  status: string;
  count: number;
}

export interface MetricsResponse {
  total_scans: number;
  unique_products: number;
  verified_count: number;
  review_count: number;
  mismatch_count: number;
  unknown_count: number;
  simulated_weight_count: number;
  real_weight_count: number;
  by_status: StatusCount[];
  scans_over_time: { date: string; count: number }[];
  top_products: { name: string; count: number }[];
}

export interface TareResponse {
  ok: boolean;
  message: string;
  sensor: SensorStatus;
}

export interface CalibrateResponse {
  ok: boolean;
  message: string;
  calibration_factor: number;
  sensor: SensorStatus;
}

export interface SensorReadingResponse {
  weight_g: number | null;
  stable: boolean;
  source: WeightSource;
  raw: number | null;
  message: string;
}

export interface DemoControlResponse {
  ok: boolean;
  message: string;
  demo: DemoStatus;
}

export interface DetectionBox {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  label: string;
  confidence: number;
  class_id: number;
  is_product: boolean;
  product_id: string | null;
  product_name: string | null;
  colour: string | null;
  colour_distribution: Record<string, number>;
  colour_quality: string;
  weight_g: number | null;
  weight_source: WeightSource;
  weight_stable: boolean;
  expected_weight_g: number | null;
  verification: VerificationStatus | null;
  explanation: string;
}

export interface WSDetectionMessage {
  type: 'ready' | 'detection' | 'status' | 'error' | 'demo' | 'pong';
  seq?: number;
  ts?: number;
  inference_ms?: number;
  fps?: number;
  mode?: InferenceMode;
  annotated?: string | null;
  boxes?: DetectionBox[];
  primary?: DetectionBox | null;
  scan_id?: string | null;
  message?: string;
  warnings?: string[];
  demo?: DemoStatus;
  fps_limit?: number;
}

export interface ScanFilters {
  product_id?: string;
  status?: VerificationStatus;
  date_from?: string;
  date_to?: string;
  search?: string;
  limit?: number;
  offset?: number;
}
