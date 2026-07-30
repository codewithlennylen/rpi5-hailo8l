from ultralytics.utils.benchmarks import ProfileModels

profiler = ProfileModels(
    ["yolov8s.onnx"],
    imgsz=640,
    num_warmup_runs=10,
    num_timed_runs=100,
)
profiler.run()
