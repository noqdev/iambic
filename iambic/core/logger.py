import logging
import os

import boto3
import structlog

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(level=LOG_LEVEL)
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper("%Y/%m/%d %H:%M:%S", utc=False),
        structlog.dev.ConsoleRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(
        logging.getLevelName(LOG_LEVEL)
    ),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=False,
)
log = structlog.get_logger("NoqForm")

if LOG_LEVEL == "DEBUG":
    boto3.set_stream_logger("", "DEBUG")
else:
    default_logging_levels = {
        "boto3": "CRITICAL",
        "boto": "CRITICAL",
        "botocore": "CRITICAL",
    }
    for logger, level in default_logging_levels.items():
        logging.getLogger(logger).setLevel(level)
