"""
Main FastAPI application for Camera API.

This module creates and configures the FastAPI application with all
necessary middleware, exception handlers, and route configurations.
"""

import logging
from datetime import datetime
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from mindtrace.hardware.api.routes import (
    backends,
    cameras,
    capture,
    config_async,
    config_persistence,
    config_sync,
    network,
)
from mindtrace.hardware.core.exceptions import (
    CameraCaptureError,
    CameraConfigurationError,
    CameraConnectionError,
    CameraError,
    CameraInitializationError,
    CameraNotFoundError,
    CameraTimeoutError,
    SDKNotAvailableError,
)
from mindtrace.hardware.models.responses import ErrorResponse

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Create FastAPI application
app = FastAPI(
    title="Camera API",
    description="REST API for camera management and control using CameraManager",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)


# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # React development server
        "http://localhost:3001",  # Alternative React port
        "http://localhost:8080",  # Alternative frontend port
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Exception mapping for camera errors
EXCEPTION_MAPPING = {
    CameraNotFoundError: (404, "CAMERA_NOT_FOUND"),
    CameraInitializationError: (409, "CAMERA_INITIALIZATION_ERROR"),
    CameraCaptureError: (422, "CAMERA_CAPTURE_ERROR"),
    CameraConfigurationError: (422, "CAMERA_CONFIGURATION_ERROR"),
    CameraConnectionError: (503, "CAMERA_CONNECTION_ERROR"),
    SDKNotAvailableError: (503, "SDK_NOT_AVAILABLE"),
    CameraTimeoutError: (408, "CAMERA_TIMEOUT"),
    CameraError: (500, "CAMERA_ERROR"),  # Generic camera error
}


@app.exception_handler(CameraError)
async def camera_error_handler(request: Request, exc: CameraError):
    """Handle camera-specific exceptions."""
    status_code, error_code = EXCEPTION_MAPPING.get(type(exc), (500, "UNKNOWN_CAMERA_ERROR"))
    
    logger.error(f"Camera error: {exc} (Request: {request.method} {request.url})")
    
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(
            success=False,
            message=str(exc),
            error_type=type(exc).__name__,
            error_code=error_code,
            timestamp=datetime.utcnow()
        ).model_dump(mode="json")
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    """Handle value errors (typically validation errors)."""
    logger.warning(f"Value error: {exc} (Request: {request.method} {request.url})")
    
    return JSONResponse(
        status_code=400,
        content=ErrorResponse(
            success=False,
            message=str(exc),
            error_type="ValueError",
            error_code="VALIDATION_ERROR",
            timestamp=datetime.utcnow()
        ).model_dump(mode="json")
    )


@app.exception_handler(KeyError)
async def key_error_handler(request: Request, exc: KeyError):
    """Handle key errors (typically missing camera or resource)."""
    logger.warning(f"Key error: {exc} (Request: {request.method} {request.url})")
    
    return JSONResponse(
        status_code=404,
        content=ErrorResponse(
            success=False,
            message=f"Resource not found: {exc}",
            error_type="KeyError",
            error_code="RESOURCE_NOT_FOUND",
            timestamp=datetime.utcnow()
        ).model_dump(mode="json")
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
    logger.error(f"Unexpected error: {exc} (Request: {request.method} {request.url})", exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            success=False,
            message="An unexpected error occurred",
            error_type=type(exc).__name__,
            error_code="INTERNAL_SERVER_ERROR",
            timestamp=datetime.utcnow()
        ).model_dump(mode="json")
    )


@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
        "service": "Camera API"
    }


@app.get("/")
async def root():
    """Root endpoint with basic API information."""
    return {
        "message": "Camera API",
        "version": "1.0.0",
        "docs_url": "/docs",
        "redoc_url": "/redoc",
        "health_url": "/health"
    }


# Middleware to log requests
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests."""
    start_time = datetime.utcnow()
    
    response = await call_next(request)
    
    process_time = (datetime.utcnow() - start_time).total_seconds()
    
    logger.info(
        f"{request.method} {request.url} - "
        f"Status: {response.status_code} - "
        f"Time: {process_time:.4f}s"
    )
    
    return response


# Include all routers
app.include_router(backends.router, prefix="/api/v1/backends", tags=["backends"])
app.include_router(cameras.router, prefix="/api/v1/cameras", tags=["cameras"])
app.include_router(config_async.router, prefix="/api/v1/cameras/config/async", tags=["config-async"])
app.include_router(config_sync.router, prefix="/api/v1/cameras/config/sync", tags=["config-sync"])
app.include_router(capture.router, prefix="/api/v1/cameras/capture", tags=["capture"])
app.include_router(config_persistence.router, prefix="/api/v1/cameras/config/persistence", tags=["config-persistence"])
app.include_router(network.router, prefix="/api/v1/network", tags=["network"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info") 