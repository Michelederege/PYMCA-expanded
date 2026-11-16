from xrfdesk.eta import fitting_label, format_remaining, percent_done, remaining_seconds


def test_remaining_time_follows_the_rate():
    assert remaining_seconds(0, 14000, 10) is None
    assert remaining_seconds(100, 400, 10) == 30
    assert remaining_seconds(400, 400, 10) == 0


def test_status_is_a_percent_and_a_time():
    assert percent_done(7000, 14000) == 50
    assert fitting_label(0, 14000, None) == "0% · estimating"
    assert fitting_label(7000, 14000, 120) == "50% · 2 min left"
    assert fitting_label(1400, 14000, 800) == "10% · 13 min left"
    assert format_remaining(45) == "45s"
    assert format_remaining(3700) == "1 h 1 min"
    assert format_remaining(7200) == "2 h"
