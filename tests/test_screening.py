from src.screening import additive_screen, passes_gates

def test_additive_screen_is_40_60():
    assert additive_screen(1, 0) == .4
    assert additive_screen(0, 1) == .6

def test_gates_require_health_safety_and_no_hard_stop():
    assert passes_gates({"creator_health": 5, "brand_safety": "PASS"})
    assert not passes_gates({"creator_health": 5, "brand_safety": "FAIL"})
