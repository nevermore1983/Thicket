"""The error handler logs details and shows friendly words, never a traceback."""

import logging

from wildlife.domain.errors import DatabaseError
from wildlife.ui.error_handler import ErrorReporter


def capture(reporter: ErrorReporter) -> list[tuple[str, str, bool]]:
    shown: list[tuple[str, str, bool]] = []
    reporter.report.disconnect(reporter._show)  # don't open a real dialog in tests
    reporter.report.connect(lambda m, d, e: shown.append((m, d, e)))
    return shown


def raise_and_handle(reporter: ErrorReporter, exc: BaseException) -> None:
    try:
        raise exc
    except BaseException as caught:
        reporter.handle(type(caught), caught, caught.__traceback__)


def test_expected_error_shows_its_own_message(qtbot, caplog):
    reporter = ErrorReporter()
    shown = capture(reporter)
    raise_and_handle(
        reporter, DatabaseError("Your data file looks damaged.", detail="quick_check failed")
    )
    message, details, expected = shown[0]
    assert message == "Your data file looks damaged." and expected
    assert "quick_check failed" in details


def test_unexpected_error_is_logged_but_user_sees_friendly_text(qtbot, caplog):
    reporter = ErrorReporter()
    shown = capture(reporter)
    with caplog.at_level(logging.CRITICAL, logger="wildlife.errors"):
        raise_and_handle(reporter, ZeroDivisionError("division by zero"))
    message, details, expected = shown[0]
    assert "Something went wrong" in message and "Traceback" not in message
    assert not expected and "ZeroDivisionError" in details
    assert "ZeroDivisionError" in caplog.text
