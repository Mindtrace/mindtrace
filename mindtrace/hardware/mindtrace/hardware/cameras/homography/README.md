# Homography Module

**Planar Measurement System for Computer Vision**

Convert pixel-space object detections to real-world metric dimensions using homography transformations.

---

## Overview

The homography module enables accurate physical measurements from camera images for objects on flat surfaces. It bridges the gap between computer vision (pixels) and physical reality (millimeters, centimeters, etc.).

**Core Capabilities:**
- ✅ Automatic checkerboard calibration
- ✅ Manual point correspondence calibration
- ✅ Real-world dimension measurement from bounding boxes
- ✅ Multi-unit support (mm, cm, m, in, ft)
- ✅ RANSAC-based robust estimation
- ✅ Framework-integrated logging and configuration

---

## Quick Start

### 1. Calibrate Camera View

```python
from mindtrace.hardware import HomographyCalibrator

# Initialize calibrator
calibrator = HomographyCalibrator()

# Calibrate using checkerboard pattern
calibration = calibrator.calibrate_checkerboard(
    image=checkerboard_image,
    board_size=(12, 12),      # Inner corners
    square_size=25.0,          # mm per square
    world_unit="mm"
)

# Save for later use
calibration.save("camera_calibration.json")
```

### 2. Measure Objects

```python
from mindtrace.hardware import HomographyMeasurer
from mindtrace.core.types import BoundingBox

# Load calibration
calibration = CalibrationData.load("camera_calibration.json")

# Initialize measurer
measurer = HomographyMeasurer(calibration)

# Measure object from detection
detection = BoundingBox(x=100, y=50, width=400, height=350)
measured = measurer.measure_bounding_box(detection, target_unit="cm")

print(f"Width: {measured.width_world:.2f} cm")
print(f"Height: {measured.height_world:.2f} cm")
print(f"Area: {measured.area_world:.2f} cm²")
```

### 3. Batch Measurement

```python
# Measure multiple objects efficiently
detections = yolo.detect(frame)  # List[BoundingBox]
measurements = measurer.measure_bounding_boxes(detections, target_unit="cm")

for measured in measurements:
    if measured.width_world > 10.0:  # Size-based filtering
        reject_oversized_part(measured)
```

---

## Architecture

### Module Structure

```
homography/
├── data.py           # CalibrationData, MeasuredBox (immutable containers)
├── calibrator.py     # HomographyCalibrator (calibration workflows)
├── measurer.py       # HomographyMeasurer (measurement operations)
└── __init__.py       # Public API exports
```

### Class Hierarchy

```
Mindtrace (base class)
├── HomographyCalibrator
│   ├── calibrate_checkerboard()      # Automatic calibration
│   ├── calibrate_from_correspondences()  # Manual calibration
│   └── estimate_intrinsics_from_fov()   # Camera model estimation
│
└── HomographyMeasurer
    ├── measure_bounding_box()         # Single object measurement
    ├── measure_bounding_boxes()       # Batch measurement
    └── pixels_to_world()              # Coordinate projection
```

### Data Structures

**CalibrationData** (Immutable)
- `H: np.ndarray` - 3x3 homography matrix
- `camera_matrix: Optional[np.ndarray]` - Camera intrinsics
- `dist_coeffs: Optional[np.ndarray]` - Distortion coefficients
- `world_unit: str` - Measurement unit (mm, cm, m, in, ft)
- Methods: `save()`, `load()`

**MeasuredBox** (Immutable)
- `corners_world: np.ndarray` - 4x2 corner coordinates
- `width_world: float` - Width in world units
- `height_world: float` - Height in world units
- `area_world: float` - Area in square world units
- `unit: str` - Measurement unit

---

## Configuration

### Environment Variables

Configure default calibration board dimensions:

```bash
# Standard 12x12 checkerboard with 25mm squares
export MINDTRACE_HW_HOMOGRAPHY_CHECKERBOARD_COLS=12
export MINDTRACE_HW_HOMOGRAPHY_CHECKERBOARD_ROWS=12
export MINDTRACE_HW_HOMOGRAPHY_CHECKERBOARD_SQUARE_SIZE=25.0
export MINDTRACE_HW_HOMOGRAPHY_DEFAULT_WORLD_UNIT=mm

# RANSAC and refinement settings
export MINDTRACE_HW_HOMOGRAPHY_RANSAC_THRESHOLD=3.0
export MINDTRACE_HW_HOMOGRAPHY_REFINE_CORNERS=true
```

### JSON Configuration

```json
{
  "homography": {
    "checkerboard_cols": 12,
    "checkerboard_rows": 12,
    "checkerboard_square_size": 25.0,
    "default_world_unit": "mm",
    "ransac_threshold": 3.0,
    "refine_corners": true
  }
}
```

### Simplified Usage with Config

```python
# Set config once
export MINDTRACE_HW_HOMOGRAPHY_CHECKERBOARD_COLS=12
export MINDTRACE_HW_HOMOGRAPHY_CHECKERBOARD_ROWS=12
export MINDTRACE_HW_HOMOGRAPHY_CHECKERBOARD_SQUARE_SIZE=25.0

# Ultra-simple calibration - all params from config!
calibrator = HomographyCalibrator()
calibration = calibrator.calibrate_checkerboard(image=img)
# Uses config defaults: 12x12 board, 25mm squares
```

---

## Calibration Methods

### Method 1: Automatic Checkerboard

**Best for:** Initial setup, camera movement verification

```python
calibrator = HomographyCalibrator()

# Detect checkerboard and compute homography
calibration = calibrator.calibrate_checkerboard(
    image=checkerboard_image,
    board_size=(12, 12),      # Inner corners (not squares!)
    square_size=25.0,          # Physical size in mm
    world_unit="mm",
    refine_corners=True        # Sub-pixel accuracy
)
```

**Requirements:**
- Checkerboard pattern visible in image
- Known square dimensions
- Good lighting and focus
- Pattern fills significant portion of frame

### Method 2: Manual Point Correspondences

**Best for:** Non-planar patterns, custom calibration targets

```python
# Known world coordinates (mm)
world_points = np.array([
    [0, 0],      # Origin
    [300, 0],    # 300mm right
    [300, 200],  # 300mm right, 200mm up
    [0, 200]     # 200mm up
])

# Corresponding pixel coordinates
image_points = np.array([
    [100, 50],   # Pixel location of origin
    [500, 50],
    [500, 400],
    [100, 400]
])

calibration = calibrator.calibrate_from_correspondences(
    world_points=world_points,
    image_points=image_points,
    world_unit="mm"
)
```

**Requirements:**
- Minimum 4 point correspondences (more is better)
- Accurate world coordinate measurements
- Precise pixel coordinate identification

### Method 3: Camera Intrinsics Estimation

**Best for:** When camera calibration unavailable

```python
# Estimate intrinsics from FOV
K = calibrator.estimate_intrinsics_from_fov(
    image_size=(1920, 1080),
    fov_horizontal_deg=70.0,
    fov_vertical_deg=45.0
)

# Use in calibration for undistortion
calibration = calibrator.calibrate_checkerboard(
    image=img,
    camera_matrix=K
)
```

---

## Measurement Operations

### Single Object Measurement

```python
measurer = HomographyMeasurer(calibration)

# From object detection
bbox = BoundingBox(x=150, y=100, width=300, height=250)
measured = measurer.measure_bounding_box(bbox, target_unit="cm")

# Access measurements
width_cm = measured.width_world       # 23.45 cm
height_cm = measured.height_world     # 18.76 cm
area_cm2 = measured.area_world        # 439.68 cm²
corners = measured.corners_world      # 4x2 array
```

### Batch Measurement

```python
# Efficient batch processing
detections = [
    BoundingBox(x=100, y=50, width=200, height=150),
    BoundingBox(x=350, y=200, width=150, height=180),
    BoundingBox(x=200, y=300, width=180, height=100),
]

measurements = measurer.measure_bounding_boxes(detections, target_unit="cm")

for i, measured in enumerate(measurements):
    print(f"Object {i+1}: {measured.width_world:.1f} × {measured.height_world:.1f} cm")
```

### Pixel-to-World Projection

```python
# Direct coordinate projection
pixel_points = np.array([[320, 240], [640, 480]])
world_points = measurer.pixels_to_world(pixel_points)

# Returns Nx2 array of world coordinates in calibration units
```

### Unit Conversion

```python
# Measure in different units
measured_mm = measurer.measure_bounding_box(bbox, target_unit="mm")
measured_cm = measurer.measure_bounding_box(bbox, target_unit="cm")
measured_in = measurer.measure_bounding_box(bbox, target_unit="in")

# Supported units: mm, cm, m, in, ft
```

---

## Use Cases

### Manufacturing QC

```python
# Verify part dimensions from overhead camera
calibrator = HomographyCalibrator()
calibration = calibrator.calibrate_checkerboard(image=calibration_img)
measurer = HomographyMeasurer(calibration)

# Measure parts on conveyor belt
for part_detection in conveyor_stream:
    measured = measurer.measure_bounding_box(part_detection, target_unit="mm")

    # Quality control checks
    if not (14.5 <= measured.width_world <= 15.5):
        reject_part("Width out of spec")
    if not (9.5 <= measured.height_world <= 10.5):
        reject_part("Height out of spec")
```

### Warehouse Automation

```python
# Measure package sizes for sorting/billing
measurements = measurer.measure_bounding_boxes(packages, target_unit="cm")

for pkg, measured in zip(packages, measurements):
    if measured.width_world > 60 or measured.height_world > 40:
        route_to_oversized_handling()
    else:
        calculate_shipping_cost(measured.width_world, measured.height_world)
```

### Agricultural Monitoring

```python
# Measure crop/fruit sizes from field cameras
fruit_detections = yolo.detect(field_image)
measurements = measurer.measure_bounding_boxes(fruit_detections, target_unit="cm")

# Grade by size
small = [m for m in measurements if m.width_world < 5.0]
medium = [m for m in measurements if 5.0 <= m.width_world < 7.0]
large = [m for m in measurements if m.width_world >= 7.0]
```

### Robotics Pick-and-Place

```python
# Enable size-aware robotic operations
target_detection = robot_vision.detect_target(camera_frame)
measured = measurer.measure_bounding_box(target_detection, target_unit="mm")

# Select appropriate gripper based on size
if measured.width_world < 20:
    robot.select_gripper("small")
elif measured.width_world < 50:
    robot.select_gripper("medium")
else:
    robot.select_gripper("large")

robot.pick(target_detection.center, measured.width_world)
```

---

## Advanced Features

### RANSAC-Based Robust Estimation

Automatically rejects outliers in point correspondences:

```python
# Configure RANSAC threshold
export MINDTRACE_HW_HOMOGRAPHY_RANSAC_THRESHOLD=5.0

# Handles noisy data gracefully
calibration = calibrator.calibrate_from_correspondences(
    world_points=noisy_world_pts,
    image_points=noisy_image_pts
)
# RANSAC automatically identifies and rejects outliers
```

### Sub-Pixel Corner Refinement

Improves calibration accuracy:

```python
# Enable sub-pixel refinement (default: enabled)
calibration = calibrator.calibrate_checkerboard(
    image=img,
    refine_corners=True  # ±0.1 pixel accuracy
)
```

### Lens Distortion Correction

Handles camera lens distortion:

```python
# Provide camera intrinsics and distortion coefficients
calibration = calibrator.calibrate_checkerboard(
    image=img,
    camera_matrix=K,
    dist_coeffs=distortion_coeffs
)
# Undistortion applied before homography computation
```

### Calibration Persistence

Save and load calibrations:

```python
# Save calibration
calibration.save("camera_1_calibration.json")

# Load later
from mindtrace.hardware.cameras.homography import CalibrationData
calibration = CalibrationData.load("camera_1_calibration.json")

# Use immediately
measurer = HomographyMeasurer(calibration)
```

---

## Limitations & Constraints

### ⚠️ Planar Surface Assumption

**The homography only works for objects on a FLAT PLANE (Z=0).**

✅ Works for:
- Overhead cameras viewing flat surfaces
- Objects on tables, floors, conveyor belts
- Parts lying flat on inspection stations

❌ Does NOT work for:
- 3D objects at varying heights
- Tilted or curved surfaces
- Objects not on the calibration plane

**Solution:** For full 3D, use stereo vision or depth cameras.

### ⚠️ Static Camera Requirement

**Camera must remain fixed after calibration.**

- Any camera movement invalidates calibration
- Pan/tilt/zoom requires recalibration
- Vibration can affect accuracy

**Solution:** Mount cameras rigidly, recalibrate after any movement.

### ⚠️ Viewing Angle Effects

**Accuracy degrades with severe perspective angles.**

- Best: Overhead view (perpendicular to plane)
- Acceptable: Up to ~30° viewing angle
- Poor: >45° viewing angle

**Solution:** Position cameras as close to perpendicular as possible.

---

## Troubleshooting

### Problem: Checkerboard Not Detected

**Symptoms:** `HardwareOperationError: Checkerboard pattern not found`

**Solutions:**
```python
# Try normalizing image
export MINDTRACE_HW_HOMOGRAPHY_CHECKERBOARD_NORMALIZE_IMAGE=true

# Adjust detection flags
export MINDTRACE_HW_HOMOGRAPHY_CHECKERBOARD_FILTER_QUADS=true

# Ensure good lighting and focus
# Ensure pattern fills significant portion of image
# Verify board_size matches actual pattern
```

### Problem: Inaccurate Measurements

**Symptoms:** Measurements don't match known dimensions

**Solutions:**
```python
# Increase corner refinement
export MINDTRACE_HW_HOMOGRAPHY_CORNER_REFINEMENT_ITERATIONS=50
export MINDTRACE_HW_HOMOGRAPHY_CORNER_REFINEMENT_WINDOW=15

# Use more point correspondences (>10)
# Check calibration plane flatness
# Verify square_size is accurate
# Test with known reference object
```

### Problem: Too Many Outliers

**Symptoms:** Few inliers reported during calibration

**Solutions:**
```python
# Relax RANSAC threshold
export MINDTRACE_HW_HOMOGRAPHY_RANSAC_THRESHOLD=5.0

# Require more correspondences
export MINDTRACE_HW_HOMOGRAPHY_MIN_CORRESPONDENCES=8

# Improve point correspondence accuracy
# Check for perspective distortion
```

---

## Performance Considerations

### Calibration Performance

- **Checkerboard detection:** ~50-200ms (depends on image size)
- **Homography computation:** ~1-5ms
- **Sub-pixel refinement:** +10-30ms

**Optimization:**
```python
# Disable refinement for speed (if accuracy allows)
calibration = calibrator.calibrate_checkerboard(
    image=img,
    refine_corners=False  # ~50% faster
)
```

### Measurement Performance

- **Single measurement:** ~0.1-0.5ms
- **Batch measurement (100 boxes):** ~10-50ms

**Optimization:**
```python
# Use batch operations
measurements = measurer.measure_bounding_boxes(boxes)  # Efficient

# Avoid individual calls in loop
for box in boxes:
    measured = measurer.measure_bounding_box(box)  # Slower
```

---

## API Reference

### HomographyCalibrator

```python
class HomographyCalibrator(Mindtrace):
    """Calibrates planar homography for pixel-to-world mapping."""

    def calibrate_checkerboard(
        image: Union[Image.Image, np.ndarray],
        board_size: Optional[Tuple[int, int]] = None,
        square_size: Optional[float] = None,
        world_unit: Optional[str] = None,
        camera_matrix: Optional[np.ndarray] = None,
        dist_coeffs: Optional[np.ndarray] = None,
        refine_corners: Optional[bool] = None
    ) -> CalibrationData

    def calibrate_from_correspondences(
        world_points: np.ndarray,
        image_points: np.ndarray,
        world_unit: Optional[str] = None,
        camera_matrix: Optional[np.ndarray] = None,
        dist_coeffs: Optional[np.ndarray] = None
    ) -> CalibrationData

    def estimate_intrinsics_from_fov(
        image_size: Tuple[int, int],
        fov_horizontal_deg: float,
        fov_vertical_deg: float,
        principal_point: Optional[Tuple[float, float]] = None
    ) -> np.ndarray
```

### HomographyMeasurer

```python
class HomographyMeasurer(Mindtrace):
    """Measures physical dimensions using planar homography."""

    def measure_bounding_box(
        box: BoundingBox,
        target_unit: Optional[str] = None
    ) -> MeasuredBox

    def measure_bounding_boxes(
        boxes: Sequence[BoundingBox],
        target_unit: Optional[str] = None
    ) -> List[MeasuredBox]

    def pixels_to_world(
        points_px: np.ndarray
    ) -> np.ndarray
```

### CalibrationData

```python
@dataclass(frozen=True)
class CalibrationData:
    H: np.ndarray
    camera_matrix: Optional[np.ndarray] = None
    dist_coeffs: Optional[np.ndarray] = None
    world_unit: str = "mm"
    plane_normal_camera: Optional[np.ndarray] = None

    def save(filepath: str) -> None

    @classmethod
    def load(filepath: str) -> CalibrationData
```

### MeasuredBox

```python
@dataclass(frozen=True)
class MeasuredBox:
    corners_world: np.ndarray  # 4x2 array
    width_world: float
    height_world: float
    area_world: float
    unit: str

    def to_dict() -> dict
```

---

## Examples

See complete examples in:
- `../../HOMOGRAPHY_CONFIG_EXAMPLES.md` - Configuration scenarios
- `../../HOMOGRAPHY_REFACTOR_SUMMARY.md` - Implementation details

---

## Integration

### With Camera Service

The homography module integrates seamlessly with the Camera Manager Service:

```python
from mindtrace.hardware import AsyncCameraManager, HomographyCalibrator, HomographyMeasurer

# Open camera
async with AsyncCameraManager() as manager:
    camera = await manager.open("Basler:camera_1")

    # Capture calibration image
    calib_img = await camera.capture()

    # Calibrate
    calibrator = HomographyCalibrator()
    calibration = calibrator.calibrate_checkerboard(calib_img)

    # Save calibration
    calibration.save(f"camera_1_calibration.json")

    # Measure objects
    measurer = HomographyMeasurer(calibration)

    while True:
        frame = await camera.capture()
        detections = detector.detect(frame)
        measurements = measurer.measure_bounding_boxes(detections, target_unit="cm")

        for measured in measurements:
            print(f"Size: {measured.width_world:.1f} × {measured.height_world:.1f} cm")
```

### With Object Detection

```python
from ultralytics import YOLO

# Initialize YOLO
yolo = YOLO("yolov8n.pt")

# Detect objects
results = yolo(frame)

# Convert to BoundingBox format
from mindtrace.core.types import BoundingBox

boxes = [
    BoundingBox(
        x=int(box.xyxy[0][0]),
        y=int(box.xyxy[0][1]),
        width=int(box.xyxy[0][2] - box.xyxy[0][0]),
        height=int(box.xyxy[0][3] - box.xyxy[0][1])
    )
    for box in results[0].boxes
]

# Measure
measurements = measurer.measure_bounding_boxes(boxes, target_unit="cm")
```

---

## License

Part of the Mindtrace Hardware framework.

---

## Support

For issues, questions, or contributions:
- Check configuration examples: `../../HOMOGRAPHY_CONFIG_EXAMPLES.md`
- Review refactor summary: `../../HOMOGRAPHY_REFACTOR_SUMMARY.md`
- See camera service integration: `../../api/cameras/README.md`
