from src.screening import additive_screen


def test_additive_screen_is_40_60():
    assert additive_screen(1, 0) == 0.4
    assert additive_screen(0, 1) == 0.6
