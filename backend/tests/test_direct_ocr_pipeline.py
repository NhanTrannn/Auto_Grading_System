import numpy as np
import pytest

from app.services.zip_intake import normalise_hs_key
from app.services import ocr_engine
from ocr_main import DetectionMismatchError, _detected_roi_config


def test_detected_roi_config_rejects_count_mismatch_without_fallback():
    configured = [
        {"cau_key": "Cau_02", "page": 1, "x": 200, "y": 300, "w": 80, "h": 40, "task_type": "short_text"},
        {"cau_key": "Cau_01", "page": 1, "x": 20, "y": 100, "w": 80, "h": 40, "task_type": "short_text"},
    ]

    with pytest.raises(DetectionMismatchError, match="detect được 1 vùng"):
        _detected_roi_config(configured, [{"x": 1, "y": 1, "w": 2, "h": 2}], 1)


def test_detected_roi_config_sorts_matching_regions_and_metadata_by_position():
    configured = [
        {"cau_key": "Cau_02", "page": 1, "x": 200, "y": 300, "w": 80, "h": 40, "task_type": "short_text"},
        {"cau_key": "Cau_01", "page": 1, "x": 20, "y": 100, "w": 80, "h": 40, "task_type": "short_text"},
    ]
    detected = [
        {"x": 210, "y": 310, "w": 80, "h": 40, "type": "fill_in_blank"},
        {"x": 30, "y": 110, "w": 80, "h": 40, "type": "fill_in_blank"},
    ]

    result = _detected_roi_config(configured, detected, 1)

    assert [roi["cau_key"] for roi in result] == ["Cau_01", "Cau_02"]
    assert [roi["x"] for roi in result] == [30, 210]


def test_normalise_hs_key_avoids_collisions():
    used = set()

    first = normalise_hs_key("HS_1", 1, used)
    second = normalise_hs_key("Student_1", 2, used)

    assert first == "HS_1"
    assert second == "HS_2"
    assert used == {"HS_1", "HS_2"}


def test_empty_image_has_no_direct_regions():
    from ocr_modules.module1 import detect_answer_regions

    image = np.full((500, 400, 3), 255, dtype=np.uint8)

    assert detect_answer_regions(image) == []
