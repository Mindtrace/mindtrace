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

export { createPlant, getPlant, listPlants, updatePlant } from "./plants";

export { createLine, getLine, listLines, updateLine } from "./lines";

export { getLineStructure, updateLineStructure } from "./line-structure";

export { createModel, getModel, listModels, updateModel } from "./models";

export {
  getModelDeployment,
  listModelDeployments,
  updateModelDeployment,
} from "./model-deployments";

export {
  getCameraService,
  listCameraServices,
  updateCameraService,
} from "./camera-services";

export {
  createCameraSet,
  deleteCameraSet,
  listCameraSets,
  updateCameraSet,
} from "./camera-sets";

export { getCamera, listCameras, updateCameraConfig } from "./cameras";

export { createStageGraph, listStageGraphs } from "./stage-graphs";

export { createStage, listStages } from "./stages";

export { upsertCameraPosition } from "./camera-positions";

export { createRoi, deleteRoi, listRois } from "./rois";

export { createUser, getUser, listUsers, updateUser } from "./users";
