from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('dataset_path', default_value=''),
        DeclareLaunchArgument('image_topic', default_value='/camera/image_raw'),
        DeclareLaunchArgument('detections_topic', default_value='/hailo/detections'),
        DeclareLaunchArgument('max_images', default_value='-1'),
        DeclareLaunchArgument('warmup_images', default_value='5'),
        DeclareLaunchArgument('timeout_sec', default_value='5.0'),
        DeclareLaunchArgument('output_csv', default_value=''),

        Node(
            package='hailo_benchmark_tools',
            executable='dataset_benchmark',
            name='dataset_benchmark_node',
            output='screen',
            parameters=[{
                'dataset_path': LaunchConfiguration('dataset_path'),
                'image_topic': LaunchConfiguration('image_topic'),
                'detections_topic': LaunchConfiguration('detections_topic'),
                'max_images': LaunchConfiguration('max_images'),
                'warmup_images': LaunchConfiguration('warmup_images'),
                'timeout_sec': LaunchConfiguration('timeout_sec'),
                'output_csv': LaunchConfiguration('output_csv'),
            }],
        ),
    ])
