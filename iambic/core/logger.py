from __future__ import annotations

import json
import logging
import os

import boto3
import structlog


def pretty_log(logger, method_name, event_dict):
    return_dict = {}

    # Uncomment this if we want to default to single line logging. Can get hard to read with long resources though.
    # if not any(bool(isinstance(value, dict) or isinstance(value, list)) for value in event_dict.values()):
    #     return event_dict

    for key, value in event_dict.items():
        if key != "event":
            key = f"\n  {key}"

        if isinstance(value, dict) or isinstance(value, list):
            value = "\n  ".join(str(json.dumps(value, indent=2)).split("\n"))

        return_dict[key] = value

    return return_dict


def configure_logger(logger_name, log_level):
    if not structlog.is_configured():
        running_on_lambda = os.getenv("AWS_LAMBDA_FUNCTION_NAME")
        renderer = (
            structlog.processors.JSONRenderer(serializer=json.dumps)
            if running_on_lambda == "aws_lambda"
            else structlog.dev.ConsoleRenderer()
        )
        structlog.configure(
            processors=[
                pretty_log,
                structlog.processors.add_log_level,
                structlog.contextvars.merge_contextvars,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper("%Y/%m/%d %H:%M:%S", utc=False),
                structlog.processors.StackInfoRenderer(),
                structlog.dev.set_exc_info,
                renderer,
            ],
            wrapper_class=structlog.make_filtering_bound_logger(
                logging.getLevelName(log_level)
            ),
            context_class=dict,
            logger_factory=structlog.PrintLoggerFactory(),
            cache_logger_on_first_use=False,
        )
    log = structlog.get_logger(logger_name)

    if log_level == "DEBUG":
        boto3.set_stream_logger("", "DEBUG")
    else:
        default_logging_levels = {
            "boto3": "CRITICAL",
            "boto": "CRITICAL",
            "botocore": "CRITICAL",
        }
        for logger, level in default_logging_levels.items():
            logging.getLogger(logger).setLevel(level)

    return log


log = configure_logger("iambic", os.getenv("LOG_LEVEL", "INFO"))
