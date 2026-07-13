"""Jetson model receive / acceptance — phase 3.

Subpackages / modules:
- ``jetson_update.testset`` — frozen field testset MANIFEST + overlap (#46)
- ``jetson_update.receiver`` — inbox ONNX scan / watch + trigger (#47)
- ``jetson_update.build_engine`` — ONNX → FP16 candidate engine via trtexec (#48)

Default inbox path: ``jetson_update/inbox/`` (see ``jetson_update/README.md``).
"""
