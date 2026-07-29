# hailo_yolo_detector

Minimal ROS2 node that runs object detection on a Hailo-8/8L NPU using
HailoRT's C++ Async Infer API directly — **no TAPPAS, no GStreamer, no
Python bindings**. This is intentional: it collapses the dependency chain
down to just `libhailort` + a `.hef` model, matching the "skip TAPPAS"
approach discussed for a ROS2 Jazzy / Ubuntu 24.04 setup.

## Prerequisites

- ROS2 Jazzy installed, sourced.
- HailoRT runtime + driver installed and version-matched
  (`hailortcli fw-control identify` should succeed with no version errors).
- HailoRT headers available (should come with the `hailort` apt package;
  confirm `/usr/include/hailo/hailort.hpp` exists).
- A compiled `.hef` model (e.g. `yolov8s.hef` from Hailo Model Zoo).
- ROS2 packages: `ros-jazzy-cv-bridge`, `ros-jazzy-vision-msgs`,
  `ros-jazzy-image-transport`.

```bash
sudo apt install ros-jazzy-cv-bridge ros-jazzy-vision-msgs ros-jazzy-image-transport
```

## Build

Drop this package into a colcon workspace:

```bash
mkdir -p ~/ros2_ws/src
cp -r hailo_yolo_detector ~/ros2_ws/src/
cd ~/ros2_ws
colcon build --packages-select hailo_yolo_detector
source install/setup.bash
```

## Run

```bash
ros2 launch hailo_yolo_detector detector.launch.py \
  hef_path:=/path/to/yolov8s.hef \
  input_topic:=/camera/image_raw
```

Detections publish on `/hailo/detections` as `vision_msgs/Detection2DArray`.
Check them with:

```bash
ros2 topic hz /hailo/detections    # your real end-to-end FPS
ros2 topic echo /hailo/detections
```

## Before this will work correctly for YOUR model

This is a working skeleton, not a drop-in-and-done solution — object
detection postprocessing is genuinely model-specific. Two things to verify
against your actual `.hef` before trusting the output:

```bash
hailortcli parse-hef /path/to/yolov8s.hef
```

1. **Input shape/format** — confirm width/height/format matches what
   `preprocess()` produces (this code assumes UINT8 RGB, plain resize,
   no letterbox padding).
2. **Output format** — `decode_detections()` assumes on-chip NMS with
   `HAILO_NMS_BY_CLASS`-style layout (per-class count + boxes), which is
   how Hailo Model Zoo ships YOLOv8 `.hef` files by default. If your
   model's output format differs, the byte layout in `decode_detections()`
   needs to change accordingly.

## Benchmarking against the CPU-only baseline

For the "quantify the Hailo advantage" comparison: run
`ros2 topic hz /hailo/detections` here, and compare against the same
image topic → CPU-only inference (e.g. ONNX Runtime or Ultralytics on the
Pi 5 CPU) → a matching detections topic. That gives you an apples-to-apples
end-to-end FPS number, as opposed to `hailortcli run --measure-fps`, which
only measures raw chip throughput without camera/preprocessing/ROS2 overhead.

## Known simplifications / follow-ups

- Inference is synchronous (blocks per frame). For higher throughput,
  pipeline it: submit frame N+1's async job while decoding frame N's result.
- No letterbox padding in preprocessing — add it if your model was
  trained/exported expecting aspect-ratio-preserving resize.
- Bindings are recreated every frame for clarity; reusing a small pool of
  pre-allocated bindings would reduce per-frame overhead further.
