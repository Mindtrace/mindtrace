import cv2
import numpy as np

from mindtrace.hardware import HomographyCalibrator, PlanarHomographyMeasurer
from mindtrace.core.types.bounding_box import BoundingBox

# Load your image
image = cv2.imread("tests/resources/checkerboard.jpg")

# Create calibrator
calibrator = HomographyCalibrator()

# Calibrate using checkerboard
# board_size: (columns, rows) of inner corners
# square_size: real-world size of each square in your chosen unit
calibration_data = calibrator.calibrate_checkerboard(
    image_bgr=image,
    board_size=(12, 12),  # 9x6 inner corners
    square_size=25.0,     # Each square is 25mm
    world_unit="mm",      # Using millimeters
    refine_corners=True
)

# Create the measurement system using your calibration
measurer = PlanarHomographyMeasurer(calibration_data)

# Load an image with objects you want to measure
#measurement_image = cv2.imread("objects_to_measure.jpg")

# Create bounding boxes around your objects (you could get these from object detection)
# BoundingBox(x, y, width, height) - where (x,y) is top-left corner
#object_box = yolo.detect_objects(measurement_image)  # In practice, you would get the bbox from object detection
object_box = BoundingBox(x=150, y=200, width=100, height=80)  # Example box

# Measure the object
measured_object = measurer.measure_bounding_box(
    box=object_box,
    target_unit="cm"  # Convert to centimeters
)

# Access the results
print(f"Object dimensions:")
print(f"Width: {measured_object.width_world:.2f} {measured_object.unit}")
print(f"Height: {measured_object.height_world:.2f} {measured_object.unit}")
print(f"Area: {measured_object.area_world:.2f} {measured_object.unit}²")
print(f"Corner coordinates: {measured_object.corners_world}")

