// API types aligned with Inspectra backend

export interface TokenResponse {
  access_token: string;
  token_type: string;
  refresh_token: string;
}

export type UserRole =
  | "super_admin"
  | "admin"
  | "user"
  | "plant_manager"
  | "line_manager"
  | "qc"
  | "ceo"
  | "mt_user";

export interface User {
  id: string;
  email: string;
  role: UserRole;
  organization_id: string;
  first_name: string;
  last_name: string;
  status: "active" | "inactive";
}

export type OrganizationStatus = "active" | "disabled";

export interface Organization {
  id: string;
  name: string;
  /** @deprecated Prefer status. True when status is "active". */
  is_active: boolean;
  status?: OrganizationStatus;
}

export interface OrganizationListResponse {
  items: Organization[];
  total: number;
}

export interface Plant {
  id: string;
  organization_id: string;
  name: string;
  location?: string | null;
}

export interface PlantListResponse {
  items: Plant[];
  total: number;
}

export type LineStatus = "pending" | "active" | "disabled" | "development";

export interface Line {
  id: string;
  organization_id: string;
  plant_id: string;
  name: string;
  status: LineStatus;
}

export interface LineListResponse {
  items: Line[];
  total: number;
}

export interface Model {
  id: string;
  name: string;
  version_id?: string | null;
  version?: string | null;
}

export interface ModelListResponse {
  items: Model[];
  total: number;
}

export type DeploymentStatus =
  | "pending"
  | "active"
  | "inactive"
  | "failed"
  | "deploying";

export type HealthStatus = "unknown" | "healthy" | "unhealthy" | "degraded";

export interface ModelDeployment {
  id: string;
  organization_id: string;
  plant_id: string;
  line_id: string;
  model_id: string;
  version_id?: string | null;
  model_server_url: string;
  deployment_status: DeploymentStatus;
  health_status: HealthStatus;
  line_name?: string | null;
  plant_name?: string | null;
  model_name?: string | null;
}

export interface ModelDeploymentListResponse {
  items: ModelDeployment[];
  total: number;
}

export type CameraBackend = "Basler";

export interface CameraService {
  id: string;
  line_id: string;
  cam_service_url: string;
  cam_service_status: DeploymentStatus;
  health_status: HealthStatus;
  backend: CameraBackend;
  line_name?: string | null;
}

export interface CameraServiceListResponse {
  items: CameraService[];
  total: number;
}

export interface CameraSet {
  id: string;
  name: string;
  line_id: string;
  line_name?: string | null;
  camera_service_id: string;
  camera_service_url: string;
  cameras: string[];
  batch_size: number;
}

export interface CameraSetListResponse {
  items: CameraSet[];
  total: number;
}

export interface StageGraph {
  id: string;
  name: string;
  stage_count: number;
}

export interface StageGraphListResponse {
  items: StageGraph[];
  total: number;
}

export interface Stage {
  id: string;
  name: string;
}

export interface StageListResponse {
  items: Stage[];
  total: number;
}

export interface CameraConfig {
  exposure_ms?: number | null;
  white_balance?: string | null;
}

export interface Camera {
  id: string;
  name: string;
  line_id: string;
  line_name?: string | null;
  camera_service_id: string;
  camera_service_url: string;
  camera_set_id?: string | null;
  // Preferred: one-to-many relationship
  camera_position_ids?: string[];
  config?: CameraConfig;
}

export interface CameraListResponse {
  items: Camera[];
  total: number;
}

export interface CameraPosition {
  id: string;
  camera_id: string;
  position: number;
}

export interface Roi {
  id: string;
  line_id: string;
  name: string;
  camera_id: string;
  camera_position_id: string;
  camera_set_id: string;
  stage_id: string;
  model_deployment_id: string;
  type: "box" | "polygon";
  points: number[][];
  holes?: number[][][];
  active: boolean;
  meta?: Record<string, unknown>;
}

export interface RoiListResponse {
  items: Roi[];
  total: number;
}

export interface UserListResponse {
  items: User[];
  total: number;
}

// Legacy health check (optional)
export interface ApiResponse {
  status: string;
  message: string;
  timestamp: string;
}
