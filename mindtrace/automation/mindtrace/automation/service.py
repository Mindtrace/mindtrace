"""AutomationService — wraps :class:`LabelStudio` as a launchable :class:`Service`.

Provides HTTP endpoints for Label Studio project management, task import,
and annotation export.

Launch::

    cm = AutomationService.launch(
        label_studio_url="http://label-studio:8080",
        api_key="your-api-key",
        host="0.0.0.0", port=9301,
    )
"""

import logging
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from mindtrace.automation import LabelStudio
from mindtrace.core import TaskSchema
from mindtrace.services import Service

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class CreateProjectRequest(BaseModel):
    """Request to create a Label Studio project."""

    name: str
    description: str = ""
    label_config: str = Field("", description="Label Studio XML label config")


class CreateProjectResponse(BaseModel):
    """Response after project creation."""

    project_id: int
    name: str


class GetProjectsRequest(BaseModel):
    """Request to list all projects."""

    pass


class GetProjectsResponse(BaseModel):
    """Response with project list."""

    projects: List[Dict[str, Any]] = Field(default_factory=list)
    count: int = 0


class GetTasksRequest(BaseModel):
    """Request to list tasks from a Label Studio project."""

    project_id: int


class GetTasksResponse(BaseModel):
    """Response with task list."""

    tasks: List[Dict[str, Any]] = Field(default_factory=list)
    count: int = 0


class ImportImagesRequest(BaseModel):
    """Request to import images from a directory as tasks."""

    project_id: int
    image_dir: str = Field(..., description="Local directory containing images")
    recursive: bool = False
    batch_size: int = 100


class ImportImagesResponse(BaseModel):
    """Response after image import."""

    tasks_created: int = 0


class ExportAnnotationsRequest(BaseModel):
    """Request to export annotations from a project."""

    project_id: int
    export_type: str = Field("YOLO", description="Export format: YOLO, COCO, VOC, JSON")
    download_all_tasks: bool = False


class ExportAnnotationsResponse(BaseModel):
    """Response with exported annotations."""

    annotations: List[Dict[str, Any]] = Field(default_factory=list)
    count: int = 0
    export_type: str = ""


class GetAnnotationsRequest(BaseModel):
    """Request to get annotations for a project or specific task."""

    project_id: int
    task_id: Optional[int] = None


class GetAnnotationsResponse(BaseModel):
    """Response with annotations."""

    annotations: List[Dict[str, Any]] = Field(default_factory=list)
    count: int = 0


class DeleteProjectRequest(BaseModel):
    """Request to delete a Label Studio project."""

    project_id: int


class DeleteProjectResponse(BaseModel):
    """Response after project deletion."""

    project_id: int
    deleted: bool = True


# ---------------------------------------------------------------------------
# TaskSchema definitions
# ---------------------------------------------------------------------------

create_project_task = TaskSchema(
    name="create_project",
    input_schema=CreateProjectRequest,
    output_schema=CreateProjectResponse,
)

get_projects_task = TaskSchema(
    name="get_projects",
    input_schema=GetProjectsRequest,
    output_schema=GetProjectsResponse,
)

get_tasks_task = TaskSchema(
    name="get_tasks",
    input_schema=GetTasksRequest,
    output_schema=GetTasksResponse,
)

import_images_task = TaskSchema(
    name="import_images",
    input_schema=ImportImagesRequest,
    output_schema=ImportImagesResponse,
)

export_annotations_task = TaskSchema(
    name="export_annotations",
    input_schema=ExportAnnotationsRequest,
    output_schema=ExportAnnotationsResponse,
)

get_annotations_task = TaskSchema(
    name="get_annotations",
    input_schema=GetAnnotationsRequest,
    output_schema=GetAnnotationsResponse,
)

delete_project_task = TaskSchema(
    name="delete_project",
    input_schema=DeleteProjectRequest,
    output_schema=DeleteProjectResponse,
)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class AutomationService(Service):
    """Launchable service wrapping :class:`mindtrace.automation.LabelStudio`.

    Exposes Label Studio project management, task import, and annotation
    export as HTTP endpoints with automatic connection manager generation.

    Args:
        label_studio_url: Base URL of the Label Studio instance.
        api_key: Label Studio API key for authentication.
        **kwargs: Forwarded to :class:`mindtrace.services.Service`.
    """

    def __init__(
        self,
        *,
        label_studio_url: str = "",
        api_key: str = "",
        email: str = "",
        password: str = "",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            summary="Automation Service",
            description=(
                "Annotation management via Label Studio — "
                "project creation, task import, and annotation export."
            ),
            **kwargs,
        )
        self._label_studio_url = label_studio_url
        self._api_key = api_key
        self._email = email
        self._password = password
        self._ls: LabelStudio | None = None

        self.add_endpoint("create_project", self._create_project, schema=create_project_task, as_tool=True)
        self.add_endpoint("get_projects", self._get_projects, schema=get_projects_task, as_tool=True)
        self.add_endpoint("get_tasks", self._get_tasks, schema=get_tasks_task, as_tool=True)
        self.add_endpoint("import_images", self._import_images, schema=import_images_task, as_tool=True)
        self.add_endpoint("export_annotations", self._export_annotations, schema=export_annotations_task, as_tool=True)
        self.add_endpoint("get_annotations", self._get_annotations, schema=get_annotations_task, as_tool=True)
        self.add_endpoint("delete_project", self._delete_project, schema=delete_project_task, as_tool=True)

        # Defer LabelStudio client creation until first use (discovery mode
        # skips live_service so the client is never needed for schema discovery).
        if kwargs.get("live_service", True):
            self._ls = LabelStudio(
                url=label_studio_url, api_key=api_key,
                email=email or None, password=password or None,
            )

        logger.info(
            "AutomationService initialised: label_studio_url=%s",
            label_studio_url,
        )

    # ------------------------------------------------------------------
    # Lazy accessor
    # ------------------------------------------------------------------

    @property
    def ls(self) -> LabelStudio:
        """Lazy-initialised Label Studio client."""
        if self._ls is None:
            self._ls = LabelStudio(
                url=self._label_studio_url, api_key=self._api_key,
                email=self._email or None, password=self._password or None,
            )
        return self._ls

    # ------------------------------------------------------------------
    # Endpoint handlers
    # ------------------------------------------------------------------

    def _create_project(self, request: CreateProjectRequest) -> CreateProjectResponse:
        """Create a new Label Studio annotation project."""
        project = self.ls.create_project(
            project_name=request.name,
            description=request.description or None,
            label_config=request.label_config or None,
        )
        return CreateProjectResponse(
            project_id=project.id if hasattr(project, "id") else int(project),
            name=request.name,
        )

    def _get_projects(self, request: GetProjectsRequest) -> GetProjectsResponse:
        """List all Label Studio projects."""
        projects = self.ls.get_projects()
        proj_list = []
        for p in projects:
            if hasattr(p, "id"):
                proj_list.append({"id": p.id, "title": getattr(p, "title", "")})
            elif isinstance(p, dict):
                proj_list.append(p)
        return GetProjectsResponse(projects=proj_list, count=len(proj_list))

    def _get_tasks(self, request: GetTasksRequest) -> GetTasksResponse:
        """List tasks from a Label Studio project."""
        tasks = self.ls.get_tasks(project_id=request.project_id)
        return GetTasksResponse(
            tasks=tasks if isinstance(tasks, list) else [],
            count=len(tasks) if isinstance(tasks, list) else 0,
        )

    def _import_images(self, request: ImportImagesRequest) -> ImportImagesResponse:
        """Import images from a local directory as Label Studio tasks."""
        import os
        if not os.path.isdir(request.image_dir):
            return ImportImagesResponse(tasks_created=0)
        result = self.ls.create_tasks_from_images(
            project_id=request.project_id,
            local_dir=request.image_dir,
            recursive=request.recursive,
            batch_size=request.batch_size,
        )
        count = result if isinstance(result, int) else len(result) if result else 0
        return ImportImagesResponse(tasks_created=count)

    def _export_annotations(self, request: ExportAnnotationsRequest) -> ExportAnnotationsResponse:
        """Export annotations from a project in the specified format."""
        try:
            annotations = self.ls.export_annotations(
                project_id=request.project_id,
                export_type=request.export_type,
                download_all_tasks=request.download_all_tasks,
            )
        except Exception:
            annotations = []
        ann_list = annotations if isinstance(annotations, list) else []
        return ExportAnnotationsResponse(
            annotations=ann_list,
            count=len(ann_list),
            export_type=request.export_type,
        )

    def _get_annotations(self, request: GetAnnotationsRequest) -> GetAnnotationsResponse:
        """Get annotations for a project or specific task."""
        annotations = self.ls.get_annotations(
            project_id=request.project_id,
            task_id=request.task_id,
        )
        ann_list = annotations if isinstance(annotations, list) else []
        return GetAnnotationsResponse(
            annotations=ann_list,
            count=len(ann_list),
        )

    def _delete_project(self, request: DeleteProjectRequest) -> DeleteProjectResponse:
        """Delete a Label Studio project."""
        self.ls.delete_project(project_id=request.project_id)
        return DeleteProjectResponse(project_id=request.project_id, deleted=True)
