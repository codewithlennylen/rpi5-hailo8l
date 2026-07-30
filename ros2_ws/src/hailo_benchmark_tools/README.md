# hailo_benchmark_tools

Dataset-driven benchmarking for object detection ROS2 nodes — no camera
required. Publishes images from a local folder one at a time to a detector
node's image topic, waits for the matching `Detection2DArray` response, and
reports per-frame latency and effective end-to-end FPS.

Designed to pair with `hailo_yolo_detector`, but it's detector-agnostic —
point `detections_topic` at any node publishing `vision_msgs/Detection2DArray`
with the input image's header preserved, including a CPU-only pipeline, for
a direct comparison against the exact same images.

## Why gated (one at a time) instead of free-running?

This publishes one image, waits for its detection result, *then* publishes
the next. That mirrors the warmup-then-measure pattern `hailortcli benchmark`
and Ultralytics' `ProfileModels` use — it gives a clean per-frame latency
number rather than a throughput number muddied by ROS2 queueing behavior.
Effective FPS is derived as `1 / mean_latency` over the timed (non-warmup)
frames.

## Install

```bash
sudo apt install python3-opencv ros-jazzy-cv-bridge ros-jazzy-vision-msgs
```

Drop into your workspace alongside `hailo_yolo_detector`:

```bash
cp -r hailo_benchmark_tools ~/ros2_ws/src/
cd ~/ros2_ws
colcon build --packages-select hailo_benchmark_tools
source install/setup.bash
```

## Get a dataset

Any folder of `.jpg`/`.png` images works. If you already ran the Ultralytics
CPU benchmark earlier (`yolo benchmark ... data=coco8.yaml`), Ultralytics
will have auto-downloaded `coco8` into a local `datasets/` folder — point
`dataset_path` at its `images/val` (or `images/train`) subdirectory to reuse
the same images across both your Ultralytics CPU numbers and this ROS2
end-to-end benchmark. Using the same images in both tools makes the two
results genuinely comparable rather than coincidentally similar.

## Run against the Hailo pipeline

In one terminal:
```bash
ros2 launch hailo_yolo_detector detector.launch.py hef_path:=/path/to/yolov8s.hef
```

In another:
```bash
ros2 run hailo_benchmark_tools dataset_benchmark --ros-args \
  -p dataset_path:=/path/to/images \
  -p image_topic:=/camera/image_raw \
  -p detections_topic:=/hailo/detections \
  -p warmup_images:=5 \
  -p output_csv:=/tmp/hailo_bench.csv
```

## Run against a CPU-only pipeline for comparison

Point a CPU-only detector node (ONNX Runtime, Ultralytics, etc.) at the same
input topic and have it publish `Detection2DArray` on a different topic
(e.g. `/cpu/detections`), preserving the incoming image's header the same
way `hailo_yolo_detector` does. Then:
```bash
ros2 run hailo_benchmark_tools dataset_benchmark --ros-args \
  -p dataset_path:=/path/to/images \
  -p image_topic:=/camera/image_raw \
  -p detections_topic:=/cpu/detections \
  -p warmup_images:=5 \
  -p output_csv:=/tmp/cpu_bench.csv
```

Same dataset, same node, two CSVs — diff the "Effective FPS" and "Mean
latency" lines for your Hailo-vs-CPU number, with per-frame data in the CSVs
if you want to plot the distribution rather than just the summary stats.

## Parameters

| Parameter | Default | Description |
|---|---|---|
| `dataset_path` | *(required)* | Folder of images (searched recursively) |
| `image_topic` | `/camera/image_raw` | Topic to publish images on |
| `detections_topic` | `/hailo/detections` | Topic to listen for `Detection2DArray` on |
| `max_images` | `-1` | Limit number of images (`-1` = all) |
| `warmup_images` | `5` | Frames excluded from summary stats |
| `timeout_sec` | `5.0` | Max wait per frame before logging a timeout and moving on |
| `output_csv` | `""` | If set, writes per-frame latency/detection-count CSV |

## Known limitations

- Strictly sequential (gated) — doesn't measure how the pipeline behaves
  under a free-running/overlapping camera feed, only steady-state per-frame
  latency. That's the right number for "how fast is inference," not
  necessarily "what FPS will my live camera topic actually sustain."
- Frame matching relies on the detector preserving `msg.header` from input
  to output (as `hailo_yolo_detector` does). A detector that doesn't forward
  the header will cause every message to be treated as stale/mismatched.
