"""Camera stream abstractions (USB + recorded video)."""

from camera.base import CameraStream, SourceType
from camera.v4l2_usb import V4L2UsbStream

__all__ = ["CameraStream", "SourceType", "V4L2UsbStream"]
