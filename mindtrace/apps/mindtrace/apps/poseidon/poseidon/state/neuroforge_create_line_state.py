import asyncio
import reflex as rx
from typing import List, Dict
import random


class CreateLineState(rx.State):
    line_name: str = ""
    location: str = ""
    integrator: str = ""
    description: str = ""
    project_name: str = ""
    inspection_zones: int = 0

    selected_brain: str = ""

    selected_cameras: List[str] = []

    camera_location_map: Dict[str, str] = {}
    captured_images: List[str] = []

    selected_images: List[str] = []
    sent_to_label_studio: bool = False

    selected_model: str = ""
    training_status: str = "idle"   # idle | running | done
    training_accuracy: float = 0.0

    deploy_status: str = "not_started"  # not_started | deploying | deployed
    is_deploying: bool = False
    deploy_progress: int = 0
    
    zone_camera_map: Dict[str, str] = {}
    exported_zip: bool = False
    
    # NEW: progress + logs
    training_progress: int = 0          # 0..100
    training_logs: List[str] = []

    @rx.event
    def set_line_name(self, v: str):
        self.line_name = v

    @rx.event
    def set_location(self, v: str):
        self.location = v

    @rx.event
    def set_integrator(self, v: str):
        self.integrator = v

    @rx.event
    def set_description(self, v: str):
        self.description = v

    @rx.event
    def select_brain(self, key: str):
        self.selected_brain = key

    @rx.event
    def toggle_camera(self, cam_id: str):
        if cam_id in self.selected_cameras:
            self.selected_cameras = [c for c in self.selected_cameras if c != cam_id]
        else:
            self.selected_cameras = [*self.selected_cameras, cam_id]

    @rx.event
    def map_camera_location(self, cam_id: str, loc: str):
        self.camera_location_map = {**self.camera_location_map, cam_id: loc}

    @rx.event
    def capture_sample(self, cam_id: str):
        img_id = f"{cam_id}-img-{len(self.captured_images) + 1}"
        self.captured_images = [img_id, *self.captured_images]

    @rx.event
    def toggle_image_select(self, img_id: str):
        if img_id in self.selected_images:
            self.selected_images = [i for i in self.selected_images if i != img_id]
        else:
            self.selected_images = [*self.selected_images, img_id]

    @rx.event
    def send_to_label_studio(self):
        self.sent_to_label_studio = True

    @rx.event
    def set_model(self, model_name: str):
        self.selected_model = model_name

    @rx.event
    def start_training(self):
        self.training_status = "running"
        self.training_accuracy = 0.91
        self.training_status = "done"

    @rx.var
    def captured_images_12(self) -> list[str]:
        return self.captured_images[:12]

    @rx.var
    def selected_images_count(self) -> int:
        return len(self.selected_images)

    @rx.var
    def training_accuracy_percent(self) -> str:
        return f"Accuracy: {self.training_accuracy:.2%}"

    @rx.event
    def deploy_model(self):
        self.deploy_status = "deploying"
        self.deploy_status = "deployed"

    def set_selected_cameras(self, ids: list[str]):
        seen = set()
        out = []
        for cid in ids:
            if cid not in seen:
                seen.add(cid)
                out.append(cid)
        self.selected_cameras = out

    @rx.event
    def select_all_cameras(self, ids: list[str]):
        self.set_selected_cameras(ids)

    @rx.event
    def clear_cameras(self):
        self.selected_cameras = []

    @rx.event
    def reset_all(self):
        self.line_name = ""
        self.location = ""
        self.integrator = ""
        self.description = ""
        self.selected_brain = ""
        self.selected_cameras = []
        self.camera_location_map = {}
        self.captured_images = []
        self.selected_images = []
        self.sent_to_label_studio = False
        self.selected_model = ""
        self.training_status = "idle"
        self.training_accuracy = 0.0
        self.deploy_status = "not_started"
        
    @rx.event
    def set_project_name(self, v: str):
        self.project_name = v

    @rx.event
    def set_inspection_zones(self, v: str):
        try:
            self.inspection_zones = int(v) if v not in (None, "") else 0
        except ValueError:
            self.inspection_zones = 0

    @rx.var
    def inspection_zones_str(self) -> str:
        return str(self.inspection_zones)

    @rx.var
    def zone_labels(self) -> list[str]:
        # ["Zone 1", ..., "Zone N"]
        return [f"Inspection Point {i}" for i in range(1, self.inspection_zones + 1)]

    # Map a zone to a camera
    def map_zone_camera(self, zone: str, cam_id: str):
        self.zone_camera_map = {**self.zone_camera_map, zone: cam_id}

    # Capture for a specific zone (uses mapped camera)
    def capture_zone_sample(self, zone: str):
        cam_id = self.zone_camera_map.get(zone, "")
        if not cam_id:
            return
        img_id = f"{zone}:{cam_id}-img-{len(self.captured_images) + 1}"
        self.captured_images = [img_id, *self.captured_images]
    
    @rx.event
    def export_selected_zip(self):
        # dummy: just flip a flag; you can hook real export later
        if len(self.selected_images) > 0:
            self.exported_zip = True

    @rx.event
    def reset_export_flag(self):
        self.exported_zip = False
        
    @rx.var
    def training_progress_label(self) -> str:
        return f"{self.training_progress}%"

    @rx.event(background=True)
    async def start_training_long(self):
        # prepare
        async with self:
            self.training_status = "running"
            self.training_progress = 0
            self.training_logs = []

        steps = [
            (5,  "Initializing training job…"),
            (15, "Loading images into dataloader…"),
            (25, f"Building model: {self.selected_model or 'AutoSelect'}"),
            (40, "Applying augmentations (flip, color jitter)…"),
            (55, "Epoch 1/3 — loss 0.73, acc 68%"),
            (70, "Epoch 2/3 — loss 0.51, acc 81%"),
            (85, "Epoch 3/3 — loss 0.38, acc 89%"),
            (92, "Validating on hold-out set…"),
            (96, "Exporting best checkpoint…"),
            (100,"Training complete."),
        ]

        for pct, msg in steps:
            async with self:
                # append log + advance progress
                self.training_logs = [*self.training_logs, msg]
                self.training_progress = pct
            await asyncio.sleep(0.35)

        # finalize
        async with self:
            # make a slightly variable accuracy just for demo effect
            self.training_accuracy = round(0.9 + random.random() * 0.08, 4)
            self.training_status = "done"

        # hop to Deploy step automatically
        return CreateLineFlowState.go_to_deploy


class CreateLineFlowState(rx.State):
    current_step: int = 1
    is_loading: bool = False

    is_deploying: bool = False
    deploy_progress: int = 0  # 0..100

    @rx.var
    def deploy_progress_label(self) -> str:
        return f"{self.deploy_progress}%"

    @rx.event
    def next(self, total: int = 7):
        self.current_step = min(self.current_step + 1, total)

    @rx.event
    def prev(self):
        self.current_step = max(1, self.current_step - 1)

    @rx.event
    def reset_flow(self):
        self.current_step = 1
        self.is_loading = False
        self.is_deploying = False
        self.deploy_progress = 0

    @rx.event
    def deploy_and_reset(self):
        return [
            CreateLineState.deploy_model,
            CreateLineState.reset_all,
            CreateLineFlowState.reset_flow,
            rx.redirect("/lines/"),
        ]

    @rx.event(background=True)
    async def deploy_with_progress(self):
        if self.is_deploying:
            return

        async with self:
            self.is_deploying = True
            self.deploy_progress = 0
        yield

        for p in (20, 40, 60, 80, 100):
            await asyncio.sleep(0.5)
            async with self:
                self.deploy_progress = p
            yield
        yield CreateLineState.deploy_model
        async with self:
            self.is_deploying = False
        yield

    @rx.event
    def go_to_deploy(self):
        self.current_step = 7
