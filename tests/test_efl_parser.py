"""Test EFL parser TOU schedule extraction.

Validates parse_tou_schedule detects and extracts hour-of-day rate periods.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from txpower.efl_parser import parse_tou_schedule, _parse_12hr
from txpower.models import RateType, TouPeriod


def test_parse_12hr_basic():
    """Verify 12-hour to 24-hour time conversion."""
    assert _parse_12hr("6am") == 6
    assert _parse_12hr("12am") == 0
    assert _parse_12hr("12pm") == 12
    assert _parse_12hr("2pm") == 14
    assert _parse_12hr("9pm") == 21
    assert _parse_12hr("11:30pm") == 23
    print("✓ _parse_12hr conversions correct")


def test_parse_tou_schedule_simple():
    """Extract peak/off-peak rates from text."""
    text = """
    Peak Rate (2:00 PM - 9:00 PM): 12.5¢ per kWh
    Off-Peak Rate (6:00 AM - 2:00 PM): 8.3¢ per kWh
    Free Nights (9:00 PM - 6:00 AM): 0¢ per kWh
    """
    schedule = parse_tou_schedule(text)
    assert len(schedule) == 3
    # Sorted by hour_start: 6, 14, 21 (wrap-around stored as 21-6, sorts to end)
    assert schedule[0].hour_start == 6 and schedule[0].hour_end == 14
    assert abs(schedule[0].rate_per_kwh - 0.083) < 0.001
    # Peak
    assert schedule[1].hour_start == 14 and schedule[1].hour_end == 21
    assert abs(schedule[1].rate_per_kwh - 0.125) < 0.001
    # Free nights (wrap-around: 21-6 means 9pm-6am)
    assert schedule[2].hour_start == 21 and schedule[2].hour_end == 6
    assert abs(schedule[2].rate_per_kwh - 0.0) < 1e-6
    print(f"✓ parse_tou_schedule extracted {len(schedule)} periods correctly")



def test_parse_tou_schedule_no_periods():
    """Return empty list when no TOU patterns found."""
    text = "This is just a fixed-rate plan with no time-based pricing."
    schedule = parse_tou_schedule(text)
    assert len(schedule) == 0
    print("✓ parse_tou_schedule returns empty list for non-TOU text")


def test_parse_tou_schedule_various_formats():
    """Handle different time and rate format variations."""
    text = """
    Peak (2pm–9pm): 12.5¢/kWh
    Off-Peak (6am - 2 pm): 0.083 $/kWh
    Free Nights (9PM to 6 AM): 0 cents per kWh
    """
    schedule = parse_tou_schedule(text)
    assert len(schedule) == 3
    # All should parse correctly despite format variations (sorted by hour_start: 6, 14, 21)
    rates = [p.rate_per_kwh for p in sorted(schedule, key=lambda p: p.hour_start)]
    assert abs(rates[0] - 0.083) < 0.001  # off-peak (6-14)
    assert abs(rates[1] - 0.125) < 0.001  # peak (14-21)
    assert abs(rates[2] - 0.0) < 1e-6  # free nights (21-6)
    print("✓ parse_tou_schedule handles various time/rate formats")


def test_parse_tou_schedule_sorted_output():
    """Verify output is sorted by hour_start."""
    text = """
    Free Nights (10pm-6am): 0¢/kWh
    Off-Peak (6am-2pm): 8¢/kWh
    Peak (2pm-10pm): 12¢/kWh
    """
    schedule = parse_tou_schedule(text)
    # Should be re-ordered by hour_start
    hours = [p.hour_start for p in schedule]
    assert hours == sorted(hours), f"Expected sorted, got {hours}"
    print("✓ parse_tou_schedule output is sorted by hour_start")


if __name__ == "__main__":
    test_parse_12hr_basic()
    test_parse_tou_schedule_simple()
    test_parse_tou_schedule_no_periods()
    test_parse_tou_schedule_various_formats()
    test_parse_tou_schedule_sorted_output()
    print("\n✓ All EFL parser TOU tests passed.")
