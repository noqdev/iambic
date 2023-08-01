from __future__ import annotations

import asyncio
import os
import pathlib
import re
import signal
import sys
import tempfile
import traceback
from typing import Optional

import click
import questionary
import requests
from pydantic import SecretStr

from iambic.config.dynamic_config import CoreConfig, ExceptionReporting
from iambic.core.logger import log

original_excepthook = sys.excepthook


class BaseException(Exception):
    def __init__(self, msg: str = "") -> None:
        self.msg = msg
        log.error("An error occurred", error=msg, exception=self.__class__.__name__)
        super().__init__(msg)

    def __str__(self):
        """Stringifies the message."""
        return self.msg


class RateLimitException(BaseException):
    """Rate Limit Exception"""


class MultipleSecretsNotAcceptedException(BaseException):
    def __init__(self):
        super().__init__("extends tag does not accept multiples secrets")


def sanitize_locals(locals_dict):
    """Replace sensitive information in a dictionary with '********'."""
    sensitive_keys = [
        "password",
        "secret",
        "token",
        "key",
    ]

    for key, value in locals_dict.items():
        if isinstance(value, SecretStr) or any(
            re.search(sensitive_key, key, re.I) for sensitive_key in sensitive_keys
        ):
            locals_dict[key] = "********"
    return locals_dict


def alarm_handler(signum, frame):
    """Raise a TimeoutError when the alarm signal is received."""
    raise TimeoutError()


def exception_reporter(exc_type, exc_value, exc_traceback):  # noqa: C901
    """Custom exception reporter function that handles reporting exceptions."""
    from iambic.config.dynamic_config import CURRENT_IAMBIC_VERSION, load_config
    from iambic.config.utils import resolve_config_template_path

    try:
        # Check if the input is coming from a terminal (TTY)
        is_tty = os.isatty(sys.stdin.fileno())
        if is_tty:
            # Set the alarm signal handler
            signal.signal(signal.SIGALRM, alarm_handler)
            # Set the alarm to go off after 5 minutes
            signal.alarm(5 * 60)

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

        # extract settings from config
        exception_reporting_settings: Optional[ExceptionReporting] = None
        automatically_send_reports = None
        detailed_reports = None
        email_address = ""

        if config:
            core_config: CoreConfig = getattr(config, "core")

            if core_config:
                exception_reporting_settings = getattr(
                    core_config, "exception_reporting"
                )

        # parse settings
        if exception_reporting_settings:
            if not exception_reporting_settings.enabled:
                return

            automatically_send_reports = (
                exception_reporting_settings.automatically_send_reports
            )
            detailed_reports = exception_reporting_settings.detailed
            email_address = exception_reporting_settings.email_address or ""

        try:
            consent = _ask_for_consent(is_tty, automatically_send_reports)
        except TimeoutError:
            consent = False
        if not consent:
            return

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

        # Include Local Variables
        include_locals = _ask_include_locals(is_tty, detailed_reports)

        if include_locals:
            # Include the local variables at each level of the traceback
            current_traceback = exc_traceback
            while current_traceback is not None:
                report += "\nLocal variables in frame:\n"
                sanitized_locals = sanitize_locals(current_traceback.tb_frame.f_locals)
                for key, value in sanitized_locals.items():
                    report += f"\t{key} = {value}\n"
                current_traceback = current_traceback.tb_next

        # Open the report in the user's favorite text editor
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tf:
            tf.write(report.encode())
            tf.close()

            if is_tty and not automatically_send_reports:
                click.edit(filename=tf.name)

            final_consent = _ask_final_consent(is_tty, automatically_send_reports, tf)
            if final_consent:
                _send_report(tf)

                # Delete the temporary file after sending the report
                os.unlink(tf.name)

                print(
                    "Thank you for reporting this error. If you would like to save these "
                    "settings, please reference the documentation on Exception Reporting. "
                    "Please also join us in Slack to discuss this issue further. "
                    "https://communityinviter.com/apps/noqcommunity/noq"
                )
    except Exception as e:
        log.error(
            "Unable to run exception reporting logic", error=str(e), exc_info=True
        )
        return


def _ask_for_consent(is_tty, automatically_send_reports):
    consent = None
    if automatically_send_reports:
        consent = True
    elif is_tty and automatically_send_reports is None:
        consent = questionary.confirm(
            "An error occurred. Would you like to report this error to us?"
            " You will have a chance to review "
            "and edit the report before sending it."
        ).ask()
    else:
        consent = False

    return consent


def _ask_include_locals(is_tty, detailed_reports):
    if detailed_reports:
        include_locals = True
    elif is_tty and detailed_reports is None:
        include_locals = questionary.confirm(
            "Would you like to include local variables in the report? "
        ).ask()
    else:
        include_locals = False
    return include_locals


def _ask_user_activity(is_tty, automatically_send_reports):
    user_activity = ""
    if is_tty and not automatically_send_reports:
        user_activity = questionary.text(
            "What were you doing at the time of the exception?"
        ).ask()

    return user_activity


def _ask_final_consent(is_tty, automatically_send_reports, tf):
    final_consent = None
    if automatically_send_reports:
        final_consent = True
        return final_consent
    if is_tty and not final_consent:
        final_consent = questionary.confirm(
            "Do you want to send this report? If not, the report will be cancelled. "
            f"You may also make last-minute edits to {tf.name} before proceeding"
        ).ask()

    return final_consent


def _send_report(tf):
    with open(tf.name, "r") as f:
        report = f.read()
    requests.post(
        "https://error-reporting-prod.iambic.org/report_exception",
        data=report,
    )


sys.excepthook = exception_reporter
