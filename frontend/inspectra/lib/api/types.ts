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
