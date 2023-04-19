from __future__ import annotations

from iambic.core.logger import log


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
