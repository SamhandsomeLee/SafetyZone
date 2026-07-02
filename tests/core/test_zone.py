"""Tests for core.zone."""

import numpy as np
import pytest

from core.zone import box_anchor, judge_zone, point_in_polygon, scale_polygon


REF = (1920, 1080)
FRAME = (960, 540)

SLOW = [(0, 0), (960, 0), (960, 540), (0, 540)]
STOP = [(200, 100), (760, 100), (760, 440), (200, 440)]


def test_scale_polygon_halves_coordinates():
    poly = scale_polygon([(100, 200), (400, 600)], REF, FRAME)
    np.testing.assert_allclose(poly[0], [50, 100])
    np.testing.assert_allclose(poly[1], [200, 300])


def test_person_anchor_bottom_center():
    assert box_anchor((10, 20, 30, 40), "person") == (20.0, 40.0)


def test_point_in_polygon_square():
    square = np.array([[0, 0], [10, 0], [10, 10], [0, 10]], dtype=float)
    assert point_in_polygon((5, 5), square)
    assert not point_in_polygon((15, 5), square)


def test_judge_stop_priority_over_slow():
    # Person anchor (cx, y2) inside scaled stop region
    box = (120, 140, 200, 210)
    hit = judge_zone(
        box,
        slow_polygon=SLOW,
        stop_polygon=STOP,
        ref_size=REF,
        frame_size=FRAME,
        anchor_mode="person",
        min_overlap=0.1,
    )
    assert hit == "stop"


def test_judge_slow_only():
    box = (50, 50, 80, 80)  # top-left in slow, outside stop
    hit = judge_zone(
        box,
        slow_polygon=SLOW,
        stop_polygon=STOP,
        ref_size=REF,
        frame_size=FRAME,
        min_overlap=0.05,
    )
    assert hit == "slow"


def test_judge_none_outside():
    box = (900, 400, 950, 530)
    hit = judge_zone(
        box,
        slow_polygon=SLOW,
        stop_polygon=STOP,
        ref_size=REF,
        frame_size=FRAME,
        min_overlap=0.5,
    )
    assert hit is None
