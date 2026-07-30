from setuptools import setup

package_name = 'hailo_benchmark_tools'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name + '/launch', ['launch/benchmark.launch.py']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Lenny Ng\'ang\'a',
    maintainer_email='codewithlennylen254@gmail.com',
    description='Dataset-driven benchmarking tool for ROS2 object detection nodes.',
    license='Apache-2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'dataset_benchmark = hailo_benchmark_tools.dataset_benchmark_node:main',
        ],
    },
)
