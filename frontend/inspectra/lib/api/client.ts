/**
 * Inspectra API client – single entry for app code.
 * Base URL: NEXT_PUBLIC_API_URL or http://localhost:8080
 *
 * Implementations live in: core (shared helpers), auth, organizations, users.
 * Add new feature modules (e.g. projects.ts, reports.ts) and re-export here.
 */

export {
  clearSessionAndRedirect,
  getApiBase,
  getSafeErrorMessage,
  isSessionOrAuthError,
  logout,
  ACCESS_TOKEN_KEY,
  REFRESH_TOKEN_KEY,
  SESSION_EXPIRED_MESSAGE,
} from "./core";

export { getMe, login, refreshTokens } from "./auth";

export {
  createOrganization,
  getOrganization,
  listOrganizations,
  updateOrganization,
} from "./organizations";

export { createUser, getUser, listUsers, updateUser } from "./users";
