"""Milestone 1 (Roadmap 31): loyalty column should be present everywhere the
power/toughness columns are, across the setup/tagging schema constants."""
import settings
from file_setup.setup_constants import CSV_PROCESSING_COLUMNS
from tagging.tag_constants import REQUIRED_COLUMNS


def test_loyalty_in_schema_constants() -> None:
    assert "loyalty" in CSV_PROCESSING_COLUMNS
    assert "loyalty" in settings.CARD_DATA_COLUMNS
    assert "loyalty" in REQUIRED_COLUMNS
