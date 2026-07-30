#!/usr/bin/env python3
"""
dataset_benchmark_node.py

Publishes images from a local folder one at a time to an object-detection
node's input topic, waits for the corresponding Detection2DArray response,
and reports per-frame latency + effective FPS. No camera required: useful
for comparing detector backends (e.g. Hailo vs CPU-only) against the exact
same image set.

Methodology note: this is a GATED benchmark: one image is published, then
we wait for its detection response before sending the next. This mirrors
the warmup-then-measure pattern of `hailortcli benchmark` and Ultralytics'
ProfileModels, giving a clean per-frame latency number rather than a
throughput number affected by queueing. Effective FPS is derived from that
latency (1 / mean_latency over the timed frames), not from a free-running
publish rate.

Usage:
  ros2 run hailo_benchmark_tools dataset_benchmark \
    --ros-args \
    -p dataset_path:=/path/to/images \
    -p image_topic:=/camera/image_raw \
    -p detections_topic:=/hailo/detections \
    -p warmup_images:=5 \
    -p timeout_sec:=5.0 \
    -p output_csv:=/tmp/hailo_bench.csv

To compare against a CPU-only pipeline, point detections_topic at that
pipeline's output topic instead and re-run against the same dataset_path.
"""

import csv
import glob
import os
import statistics
import sys
import time

import cv2
import rclpy
from cv_bridge import CvBridge
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image
from vision_msgs.msg import Detection2DArray

IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.bmp')


class DatasetBenchmarkNode(Node):
    def __init__(self):
        super().__init__('dataset_benchmark_node')

        self.declare_parameter('dataset_path', '')
        self.declare_parameter('image_topic', '/camera/image_raw')
        self.declare_parameter('detections_topic', '/hailo/detections')
        self.declare_parameter('max_images', -1)
        self.declare_parameter('warmup_images', 5)
        self.declare_parameter('timeout_sec', 5.0)
        self.declare_parameter('output_csv', '')

        self.dataset_path = self.get_parameter('dataset_path').value
        self.image_topic = self.get_parameter('image_topic').value
        self.detections_topic = self.get_parameter('detections_topic').value
        self.max_images = self.get_parameter('max_images').value
        self.warmup_images = self.get_parameter('warmup_images').value
        self.timeout_sec = self.get_parameter('timeout_sec').value
        self.output_csv = self.get_parameter('output_csv').value

        if not self.dataset_path or not os.path.isdir(self.dataset_path):
            self.get_logger().error(
                f"dataset_path '{self.dataset_path}' is not a valid directory. "
                "Set it with -p dataset_path:=/path/to/images")
            sys.exit(1)

        self.image_files = sorted(
            f for f in glob.glob(os.path.join(self.dataset_path, '**', '*'), recursive=True)
            if f.lower().endswith(IMAGE_EXTENSIONS)
        )
        if not self.image_files:
            self.get_logger().error(f"No images found under {self.dataset_path}")
            sys.exit(1)
        if self.max_images > 0:
            self.image_files = self.image_files[:self.max_images]

        self.get_logger().info(f"Loaded {len(self.image_files)} images from {self.dataset_path}")

        self.bridge = CvBridge()

        qos = QoSProfile(depth=1,
                          reliability=ReliabilityPolicy.RELIABLE,
                          history=HistoryPolicy.KEEP_LAST)

        self.image_pub = self.create_publisher(Image, self.image_topic, qos)
        self.detection_sub = self.create_subscription(
            Detection2DArray, self.detections_topic, self._on_detection, qos)

        self._awaiting_frame_id = None
        self._t_publish = None
        self._t_received = None
        self._num_detections_received = 0

        self.results = []  # dicts: index, filename, latency_s, num_detections, warmup

    def _on_detection(self, msg: Detection2DArray):
        if self._awaiting_frame_id is None:
            return  # not currently waiting on anything (stale/late message)
        if msg.header.frame_id != self._awaiting_frame_id:
            self.get_logger().warn(
                f"Got response for frame_id={msg.header.frame_id} while waiting on "
                f"{self._awaiting_frame_id}; ignoring (likely a late reply after a timeout).")
            return
        self._t_received = time.perf_counter()
        self._num_detections_received = len(msg.detections)

    def run(self):
        self.get_logger().info(
            f"Publishing on {self.image_topic}, listening on {self.detections_topic}. "
            f"Warmup frames: {self.warmup_images}, timeout: {self.timeout_sec}s")

        for i, path in enumerate(self.image_files):
            img = cv2.imread(path)
            if img is None:
                self.get_logger().warn(f"Could not read {path}, skipping")
                continue

            msg = self.bridge.cv2_to_imgmsg(img, encoding='bgr8')
            frame_id = str(i)
            msg.header.frame_id = frame_id
            msg.header.stamp = self.get_clock().now().to_msg()

            self._awaiting_frame_id = frame_id
            self._t_received = None
            self._num_detections_received = 0

            self._t_publish = time.perf_counter()
            self.image_pub.publish(msg)

            deadline = self._t_publish + self.timeout_sec
            while self._t_received is None and time.perf_counter() < deadline:
                rclpy.spin_once(self, timeout_sec=0.05)

            self._awaiting_frame_id = None

            if self._t_received is None:
                self.get_logger().warn(f"[{i}] TIMEOUT waiting for detection on {os.path.basename(path)}")
                continue

            latency = self._t_received - self._t_publish
            is_warmup = i < self.warmup_images
            self.results.append({
                'index': i,
                'filename': os.path.basename(path),
                'latency_s': latency,
                'num_detections': self._num_detections_received,
                'warmup': is_warmup,
            })

            tag = '(warmup)' if is_warmup else ''
            self.get_logger().info(
                f"[{i + 1}/{len(self.image_files)}] {os.path.basename(path)}: "
                f"{latency * 1000:.1f} ms, {self._num_detections_received} detections {tag}")

        self._report()

    def _report(self):
        timed = [r for r in self.results if not r['warmup']]
        if not timed:
            self.get_logger().error("No timed results collected (all warmup, or all timed out).")
            return

        latencies = [r['latency_s'] for r in timed]
        mean_lat = statistics.mean(latencies)
        median_lat = statistics.median(latencies)
        stdev_lat = statistics.stdev(latencies) if len(latencies) > 1 else 0.0
        p95_lat = sorted(latencies)[int(0.95 * (len(latencies) - 1))]
        min_lat = min(latencies)
        max_lat = max(latencies)
        total_time = sum(latencies)
        fps = len(latencies) / total_time if total_time > 0 else 0.0
        total_detections = sum(r['num_detections'] for r in timed)
        timeouts = len(self.image_files) - len(self.results)

        print("\n" + "=" * 60)
        print(f"Dataset benchmark: {self.image_topic} -> {self.detections_topic}")
        print("=" * 60)
        print(f"Images loaded:        {len(self.image_files)}")
        print(f"Warmup (excluded):    {self.warmup_images}")
        print(f"Timed frames:         {len(timed)}")
        print(f"Timeouts (approx):    {timeouts}")
        print(f"Total detections:     {total_detections}  ({total_detections / len(timed):.2f} avg/frame)")
        print("-" * 60)
        print(f"Mean latency:         {mean_lat * 1000:.2f} ms")
        print(f"Median latency:       {median_lat * 1000:.2f} ms")
        print(f"Std dev:              {stdev_lat * 1000:.2f} ms")
        print(f"Min / Max latency:    {min_lat * 1000:.2f} / {max_lat * 1000:.2f} ms")
        print(f"P95 latency:          {p95_lat * 1000:.2f} ms")
        print(f"Effective FPS:        {fps:.2f}")
        print("=" * 60 + "\n")

        if self.output_csv:
            with open(self.output_csv, 'w', newline='') as f:
                writer = csv.DictWriter(
                    f, fieldnames=['index', 'filename', 'latency_s', 'num_detections', 'warmup'])
                writer.writeheader()
                writer.writerows(self.results)
            self.get_logger().info(f"Wrote per-frame results to {self.output_csv}")


def main(args=None):
    rclpy.init(args=args)
    node = DatasetBenchmarkNode()
    try:
        node.run()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
