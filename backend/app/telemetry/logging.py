from __future__ import annotations

import logging


class PrivacyLogFilter(logging.Filter):
    """Remove free-text messages and exception details from application logs."""

    def filter(self, record: logging.LogRecord) -> bool:
        is_error = record.levelno >= logging.ERROR
        record.msg = "application_error" if is_error else "application_event"
        record.args = ()
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None

        for attribute in (
            "answer",
            "email",
            "ip",
            "ip_address",
            "prompt",
            "question",
            "request_body",
            "response",
            "student_id",
            "transcript",
            "user_id",
        ):
            record.__dict__.pop(attribute, None)
        return True


def install_privacy_log_filter() -> None:
    root_logger = logging.getLogger()
    privacy_filter = next(
        (item for item in root_logger.filters if isinstance(item, PrivacyLogFilter)),
        None,
    )
    if privacy_filter is None:
        privacy_filter = PrivacyLogFilter()
        root_logger.addFilter(privacy_filter)

    for handler in root_logger.handlers:
        if not any(isinstance(item, PrivacyLogFilter) for item in handler.filters):
            handler.addFilter(privacy_filter)
