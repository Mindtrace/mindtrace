"""InspectionApp: hardware-driven inspection pipeline with job queue integration.

Ties together:
  - Hardware: AbstractCamera + AbstractPLC + AbstractScanner  (mindtrace-hardware)
  - Model service: any ModelService                          (mindtrace-services)
  - Jobs: Orchestrator for async job dispatch               (mindtrace-jobs)
  - Datalake: async result storage                          (mindtrace-datalake)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable

from mindtrace.core import Mindtrace


@dataclass
class InspectionAppConfig:
    """Runtime configuration for InspectionApp."""

    app_name: str = "inspection_app"
    store_results: bool = True  # write predictions to datalake
    store_images: bool = False  # also write raw frames
    result_schema: str = "inspection_result"
    max_queue_depth: int = 64  # job queue backpressure limit
    transform: Callable | None = None  # frame → model input transform
    metadata: dict = field(default_factory=dict)


class InspectionApp(Mindtrace):
    """Camera-triggered inspection loop.

    Acquires frames from a camera, runs a model service, optionally stores
    results in the datalake, and dispatches long-running tasks via the job queue.

    Example::

        app = InspectionApp(
            camera=MockCamera(),
            service=classifier_service,
            config=InspectionAppConfig(app_name="weld_inspection"),
        )
        asyncio.run(app.run(num_frames=100))
    """

    def __init__(
        self,
        camera: Any,
        service: Any,
        config: InspectionAppConfig | None = None,
        datalake: Any | None = None,
        plc: Any | None = None,
        orchestrator: Any | None = None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.camera = camera
        self.service = service
        self.config = config or InspectionAppConfig()
        self.datalake = datalake
        self.plc = plc
        self.orchestrator = orchestrator
        self._running = False

    async def _acquire(self) -> Any:
        """Acquire a single frame from the camera."""
        if asyncio.iscoroutinefunction(self.camera.acquire):
            return await self.camera.acquire()
        return await asyncio.to_thread(self.camera.acquire)

    def _infer(self, frame: Any) -> Any:
        """Run the model service on a frame."""
        inp = self.config.transform(frame) if self.config.transform else frame
        return self.service.predict(inp)

    async def _store(self, frame: Any, prediction: Any) -> None:
        """Persist result (and optionally the raw frame) to the datalake."""
        if self.datalake is None or not self.config.store_results:
            return
        payload: dict = {
            "schema": self.config.result_schema,
            "prediction": prediction,
            **self.config.metadata,
        }
        if self.config.store_images:
            payload["frame"] = frame
        try:
            if asyncio.iscoroutinefunction(self.datalake.store_data):
                await self.datalake.store_data(payload)
            else:
                await asyncio.to_thread(self.datalake.store_data, payload)
        except Exception as exc:
            self.logger.warning(f"Failed to store result: {exc}")

    async def _signal_plc(self, prediction: Any) -> None:
        """Write a verdict tag back to the PLC if one is configured."""
        if self.plc is None:
            return
        verdict = prediction.get("verdict") if isinstance(prediction, dict) else str(prediction)
        try:
            write = self.plc.write_tag if hasattr(self.plc, "write_tag") else None
            if write:
                if asyncio.iscoroutinefunction(write):
                    await write("inspection_result", verdict)
                else:
                    await asyncio.to_thread(write, "inspection_result", verdict)
        except Exception as exc:
            self.logger.warning(f"PLC write failed: {exc}")

    async def run(self, num_frames: int | None = None) -> list[dict]:
        """Run the inspection loop.

        Args:
            num_frames: Stop after this many frames. None = run until stopped.

        Returns:
            List of result dicts: ``{"frame_idx", "prediction"}``.
        """
        self._running = True
        results: list[dict] = []
        frame_idx = 0
        self.logger.info(
            f"InspectionApp '{self.config.app_name}' starting (frames={'∞' if num_frames is None else num_frames})"
        )
        try:
            while self._running and (num_frames is None or frame_idx < num_frames):
                try:
                    frame = await self._acquire()
                    prediction = await asyncio.to_thread(self._infer, frame)
                    await asyncio.gather(
                        self._store(frame, prediction),
                        self._signal_plc(prediction),
                    )
                    result = {"frame_idx": frame_idx, "prediction": prediction}
                    results.append(result)
                    self.logger.debug(f"Frame {frame_idx}: {prediction}")
                except Exception as exc:
                    self.logger.error(f"Frame {frame_idx} error: {exc}")
                frame_idx += 1
        finally:
            self._running = False
            self.logger.info(f"InspectionApp '{self.config.app_name}' stopped after {frame_idx} frames")
        return results

    def stop(self) -> None:
        """Signal the run loop to stop after the current frame."""
        self._running = False
