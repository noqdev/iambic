from __future__ import annotations

import asyncio
import os
import pathlib
import re
import signal
import sys
import tempfile
import traceback
from types import TracebackType
from typing import TYPE_CHECKING, Optional

import click
import questionary
import requests
from pydantic import SecretStr

from iambic.core.logger import log

if TYPE_CHECKING:
    from iambic.config.dynamic_config import Config, CoreConfig, ExceptionReporting

original_excepthook = sys.excepthook

TIMEOUT = int(5 * 60)  # 5 minutes


class BaseException(Exception):
    def __init__(self, msg: str = "") -> None:
        self.msg = msg
        if not isinstance(self, ExceptionReportingDisabledException):
            log.error(
                "An error occurred",
                error=msg,
                exception=self.__class__.__name__,
                stacktrace="".join(
                    traceback.format_list(traceback.extract_stack())[:-1]
                ),
            )
        super().__init__(msg)

    def __str__(self):
        """Stringifies the message."""
        return self.msg


class RateLimitException(BaseException):
    """Rate Limit Exception"""

    def __init__(self, msg="Rate limit exceeded"):
        super().__init__(msg)


class MultipleSecretsNotAcceptedException(BaseException):
    def __init__(self):
        super().__init__("extends tag does not accept multiples secrets")


class ExceptionReportingDisabledException(BaseException):
    def __init__(self):
        super().__init__("Exception reporting is disabled")


def sanitize_locals(locals_dict):
    """Replace sensitive information in a dictionary with '********'."""
    sensitive_keys = ["password", "secret", "token", "key", "private"]

    for key, value in locals_dict.items():
        if isinstance(value, SecretStr) or any(
            re.search(sensitive_key, key, re.I) for sensitive_key in sensitive_keys
        ):
            locals_dict[key] = "********"
    return locals_dict


def alarm_handler(signum, frame):
    """Raise a TimeoutError when the alarm signal is received."""
    print()  # Print a blank line to separate the error message from the prompt
    log.error(
        "Timed out waiting for user input. Please report this error to the IAMbic team."
    )
    raise TimeoutError("Timed out waiting for user input")


def exception_reporter(exc_type, exc_value, exc_traceback: TracebackType | None):
    """Custom exception reporter function that handles reporting exceptions."""
    from iambic.config.dynamic_config import load_config
    from iambic.config.utils import resolve_config_template_path

    if not isinstance(exc_value, BaseException):
        log.error(
            "Unhandled Exception",
            error=exc_value,
            exception=exc_type.__name__,
            stacktrace="".join(
                traceback.format_list(traceback.extract_tb(exc_traceback))
            ),
        )

    try:
        # Check if the input is coming from a terminal (TTY)
        is_tty = os.isatty(sys.stdin.fileno())
        if is_tty:
            # Set the alarm signal handler
            signal.signal(signal.SIGALRM, alarm_handler)
            # Set the alarm to go off after 5 minutes
            signal.alarm(TIMEOUT)

        repo_directory = os.environ.get("IAMBIC_REPO_DIR", str(pathlib.Path.cwd()))
        config = None

        try:
            config_path = asyncio.run(
                resolve_config_template_path(repo_dir=repo_directory)
            )
            # load_config is required to populate known templates
            config = asyncio.run(load_config(config_path, configure_plugins=False))
        except Exception as e:
            # If config fails, prompt if TTY otherwise return
            log.error("Unable to load config", error=str(e), exc_info=True)
            if not is_tty:
                return

        (
            _,
            automatically_send_reports,
            include_variables,
            email_address,
        ) = _extract_settings(config, is_tty)

        consent = _ask_for_consent(is_tty, automatically_send_reports)

        if not consent:
            return

        report = _generate_report(
            exc_value,
            exc_traceback,
            is_tty,
            automatically_send_reports,
            email_address,
        )

        # Include Local Variables
        include_locals = _ask_include_locals(is_tty, include_variables)
        report = _add_locals(exc_traceback, report, include_locals)

        # Open the report in the user's favorite text editor
        tf = _generate_temp_file(is_tty, automatically_send_reports, report)
        final_consent = _ask_final_consent(is_tty, automatically_send_reports, tf)

        if not final_consent:
            return

        _send_report(tf)

        # Delete the temporary file after sending the report
        os.unlink(tf.name)

        if is_tty:
            print(
                "Thank you for reporting this error. If you would like to save these "
                "settings to automatically send reports, please reference the documentation "
                "on Exception Reporting. "
                "Please also join us in Slack to discuss this issue further. "
                "https://communityinviter.com/apps/noqcommunity/noq"
            )
    except ExceptionReportingDisabledException:
        return
    except TimeoutError:
        return
    except Exception as e:
        log.error(
            "Unable to run exception reporting logic", error=str(e), exc_info=True
        )
        return


def _extract_settings(
    config: Optional[Config], is_tty: bool
) -> tuple[Optional[ExceptionReporting], Optional[bool], Optional[bool], str]:
    # extract settings from config
    exception_reporting_settings: Optional[ExceptionReporting] = None
    automatically_send_reports = None
    include_variables = False
    email_address = ""

    if config:
        core_config: CoreConfig = getattr(config, "core")

        if core_config:
            exception_reporting_settings = getattr(core_config, "exception_reporting")

    # parse settings
    if exception_reporting_settings:
        if not exception_reporting_settings.enabled:
            raise ExceptionReportingDisabledException()

        automatically_send_reports = (
            exception_reporting_settings.automatically_send_reports
        )
        include_variables = exception_reporting_settings.include_variables
        email_address = exception_reporting_settings.email_address or ""
    elif is_tty and not os.getenv("AWS_LAMBDA_FUNCTION_NAME"):
        # show message if exception reporting is not configured
        questionary.print(
            "You can configure exception reporting in your config file. "
            "Please see the docs at "
            "https://docs.iambic.org/reference/iambic-exception-reporting "
            "for more information."
        )

    return (
        exception_reporting_settings,
        automatically_send_reports,
        include_variables,
        email_address,
    )


def _generate_temp_file(
    is_tty: bool, automatically_send_reports: Optional[bool], report: str
):
    tf = tempfile.NamedTemporaryFile(suffix=".txt", delete=False)
    tf.write(report.encode())
    tf.close()

    if is_tty and not automatically_send_reports:
        click.edit(filename=tf.name)

    return tf


def _add_locals(
    exc_traceback: TracebackType | None,
    report: str,
    include_locals: bool,
) -> str:
    if include_locals:
        # Include the local variables at each level of the traceback
        current_traceback = exc_traceback
        while current_traceback is not None:
            report += "\nLocal variables in frame:\n"
            sanitized_locals = sanitize_locals(current_traceback.tb_frame.f_locals)
            for key, value in sanitized_locals.items():
                report += f"\t{key} = {value}\n"
            current_traceback = current_traceback.tb_next
    return report


def _generate_report(
    exc_value,
    exc_traceback: TracebackType | None,
    is_tty: bool,
    automatically_send_reports: Optional[bool],
    email_address: str,
) -> str:
    from iambic.config.dynamic_config import CURRENT_IAMBIC_VERSION

    report = "Please review, edit, and save the report before sending it to us.\n"
    report += "\nEmail (Optional): " + email_address
    report += "\nIAMbic Version: " + CURRENT_IAMBIC_VERSION

    # Include user_activity
    user_activity = _ask_user_activity(is_tty, automatically_send_reports)
    report += "\nUser activity: " + user_activity
    report += "\nException: " + str(exc_value)

    # Format the traceback
    formatted_traceback = "".join(traceback.format_tb(exc_traceback))
    log.error("The error occurred:\n" + formatted_traceback)
    report += "\nTraceback:\n" + formatted_traceback
    return report


def _ask_for_consent(is_tty: bool, automatically_send_reports: Optional[bool]) -> bool:
    if automatically_send_reports:
        return True

    if is_tty and automatically_send_reports is None:
        return questionary.confirm(
            "An error occurred. Would you like to report this error to us?"
            " You will have a chance to review "
            "and edit the report before sending it."
        ).ask()

    return False


def _ask_include_locals(is_tty: bool, include_variables: Optional[bool]) -> bool:
    """Ask the user if they want to include local variables in the report.
    If the user is not in a TTY, then we will not ask them and
    will instead use the value directly.
    """
    if is_tty and include_variables is True:
        return questionary.confirm(
            "Would you like to include local variables in the report? "
        ).ask()

    return not is_tty and include_variables is True


def _ask_user_activity(is_tty: bool, automatically_send_reports: Optional[bool]) -> str:
    if is_tty and not automatically_send_reports:
        return questionary.text(
            "What were you doing at the time of the exception?"
        ).ask()

    return ""


def _ask_final_consent(
    is_tty: bool, automatically_send_reports: Optional[bool], tf
) -> Optional[bool]:
    if automatically_send_reports:
        return True

    if is_tty:
        return questionary.confirm(
            "Do you want to send this report? If not, the report will be cancelled. "
            f"You may also make last-minute edits to {tf.name} before proceeding"
        ).ask()

    return None


def _send_report(tf):
    with open(tf.name, "r") as f:
        report = f.read()
    requests.post(
        "https://error-reporting-prod.iambic.org/report_exception",
        data=report,
    )


sys.excepthook = exception_reporter
