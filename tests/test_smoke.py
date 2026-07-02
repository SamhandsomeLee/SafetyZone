def test_core_public_exports():
    import core

    assert core.load_config is not None
    assert core.postprocess_yolo is not None
    assert core.DetectionHold is not None
