from PIL import Image

from mindtrace.core.types.bounding_box import BoundingBox
from mindtrace.hardware import HomographyCalibrator, PlanarHomographyMeasurer

# Load your image (PIL is now the preferred format)
image = Image.open("tests/resources/checkerboard.jpg")

# Create calibrator
calibrator = HomographyCalibrator()

# Calibrate using checkerboard
# board_size: (columns, rows) of inner corners
# square_size: real-world size of each square in your chosen unit
calibration_data = calibrator.calibrate_checkerboard(
    image=image,  # PIL Image (preferred) or numpy array (backward compatible)
    board_size=(12, 12),  # 12x12 inner corners
    square_size=25.0,  # Each square is 25mm
    world_unit="mm",  # Using millimeters
    refine_corners=True,
)

# Create the measurement system using your calibration
measurer = PlanarHomographyMeasurer(calibration_data)

# Load an image with objects you want to measure
# measurement_image = cv2.imread("objects_to_measure.jpg")

# Create bounding boxes around your objects (you could get these from object detection)
# BoundingBox(x, y, width, height) - where (x,y) is top-left corner
# object_box = yolo.detect_objects(measurement_image)  # In practice, you would get the bbox from object detection
object_box = BoundingBox(x=150, y=200, width=100, height=80)  # Example box

# Measure the object in different units
measured_object_mm = measurer.measure_bounding_box(
    box=object_box,
    target_unit="mm",  # Default unit from calibration
)

measured_object_in = measurer.measure_bounding_box(
    box=object_box,
    target_unit="in",  # Convert to inches
)

measured_object_ft = measurer.measure_bounding_box(
    box=object_box,
    target_unit="ft",  # Convert to feet
)

# Access the results
print("Object dimensions in different units:")
print(
    f"Millimeters - Width: {measured_object_mm.width_world:.2f} {measured_object_mm.unit}, Height: {measured_object_mm.height_world:.2f} {measured_object_mm.unit}"
)
print(
    f"Inches - Width: {measured_object_in.width_world:.3f} {measured_object_in.unit}, Height: {measured_object_in.height_world:.3f} {measured_object_in.unit}"
)
print(
    f"Feet - Width: {measured_object_ft.width_world:.4f} {measured_object_ft.unit}, Height: {measured_object_ft.height_world:.4f} {measured_object_ft.unit}"
)
print(f"Area: {measured_object_in.area_world:.3f} {measured_object_in.unit}²")
print(f"Corner coordinates: {measured_object_mm.corners_world}")
