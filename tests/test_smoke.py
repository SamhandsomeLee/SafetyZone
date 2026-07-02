def test_package_imports():
    import core
    import camera

    assert core.IntrusionFSM is not None
    assert camera.CameraStream is not None
