from mindtrace.hardware.api.cameras.service import CameraManagerService

if __name__ == "__main__":
    # Launch the camera service
    connection_manager = CameraManagerService.launch(
        host="192.168.50.32",
        port=8002,
        wait_for_launch=True,
        block=True  # Keep the service running
    )