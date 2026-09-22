# STUB: AC-0220
# tests/quarantine/test_parser_admits.py
import pytest

from ced.domain.quarantine.parser import AdmittedTypeRefused, admit


def test_free_text_is_refused() -> None:
    with pytest.raises(AdmittedTypeRefused):
        admit("Apple reported record revenue this quarter.")


def test_a_closed_vocabulary_label_is_admitted() -> None:
    assert admit("revenue-recognition") == "revenue-recognition"
