from ultralytics import YOLO

# Load the small model (downloads automatically if missing)
model = YOLO("yolov8s.pt")

# Export to ONNX format
model.export(format="onnx")
