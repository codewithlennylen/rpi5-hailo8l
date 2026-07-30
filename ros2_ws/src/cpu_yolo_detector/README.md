# cpu_yolo_detector

CPU-only YOLOv8 object detection ROS2 node using ONNX Runtime — the direct
counterpart to `hailo_yolo_detector`, for benchmarking the Hailo accelerator's
actual advantage on the Pi 5.

Same `vision_msgs/Detection2DArray` output format, same header-preservation
convention as `hailo_yolo_detector` — so `hailo_benchmark_tools` works
against this node with no changes, just point `detections_topic` at
`/cpu/detections` instead of `/hailo/detections`.

## Install

```bash
sudo apt install python3-opencv python3-numpy ros-jazzy-cv-bridge ros-jazzy-vision-msgs
pip install onnxruntime --break-system-packages
```

`onnxruntime` isn't a rosdep-resolvable key, hence the separate `pip install`
rather than `rosdep install` picking it up automatically.

Build:

```bash
cp -r cpu_yolo_detector ~/ros2_ws/src/
cd ~/ros2_ws
colcon build --packages-select cpu_yolo_detector
source install/setup.bash
```

## Get a matching ONNX model

```bash
yolo export model=yolov8s.pt format=onnx imgsz=640
```

## Run

```bash
ros2 launch cpu_yolo_detector cpu_detector.launch.py \
  model_path:=/path/to/yolov8s.onnx \
  input_topic:=/camera/image_raw
```

## Benchmark against hailo_yolo_detector

```bash
ros2 run hailo_benchmark_tools dataset_benchmark --ros-args \
  -p dataset_path:=/path/to/images \
  -p image_topic:=/camera/image_raw \
  -p detections_topic:=/cpu/detections \
  -p warmup_images:=5 \
  -p output_csv:=/tmp/cpu_bench.csv
```

Run this, then run the same command with `detections_topic:=/hailo/detections`
against `hailo_yolo_detector` (from a separate earlier run) — same dataset,
same benchmark tool, two CSVs to diff.

## Fairness notes for interpreting the result

- **Precision mismatch is real and expected.** Your `.hef` runs int8
  (quantized during Hailo compilation); this ONNX model runs fp32 by
  default. Part of the FPS gap observed is attributable to that, not
  purely "NPU vs CPU" in the abstract; this mirrors the same caveat
  from the `hailortcli benchmark` vs Ultralytics CPU benchmark comparison.
- **`num_threads` matters.** Default is 4 to use all of the Pi 5's cores;
  lower it if your actual ROS2 graph will have other nodes competing for
  CPU at the same time as detection, since that's the more realistic
  number.
- **Preprocessing must match.** This uses letterbox resize (aspect-ratio
  preserving, padded to square). `hailo_yolo_detector`'s current
  `preprocess()` uses a plain resize (no letterbox)

## Known limitations

- Standard (non-NMS-baked) ONNX export assumed. If you exported with
  `nms=True`, `postprocess()` needs to change to consume the different
  output format.
- Synchronous, single-frame-at-a-time inference: no batching, matching
  `hailo_yolo_detector`'s batch size of 1 for a fair comparison.
