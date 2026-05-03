"""Domain errors for HEPData access."""

from http import HTTPStatus


class HEPDataError(Exception):
    """Base class for user-safe HEPData client errors."""


class HEPDataIdentifierError(HEPDataError, ValueError):
    """Raised when a record identifier cannot be represented safely."""


class HEPDataFormatError(HEPDataError, ValueError):
    """Raised when a requested export or table format is unsupported."""


class HEPDataResponseTooLargeError(HEPDataError):
    """Raised when a HEPData response exceeds the configured byte limit."""

    def __init__(self, url: str, limit_bytes: int) -> None:
        super().__init__(f"HEPData response exceeded {limit_bytes} bytes: {url}")
        self.url = url
        self.limit_bytes = limit_bytes


class HEPDataHTTPError(HEPDataError):
    """Raised when HEPData returns a non-successful HTTP response."""

    def __init__(self, status_code: int, url: str, detail: str | None = None) -> None:
        try:
            reason = HTTPStatus(status_code).phrase
        except ValueError:
            reason = "HTTP error"
        message = f"HEPData returned {status_code} {reason}: {url}"
        if detail:
            message = f"{message}. {detail}"
        super().__init__(message)
        self.status_code = status_code
        self.url = url
        self.detail = detail


class HEPDataTransportError(HEPDataError):
    """Raised when HEPData cannot be reached."""

    def __init__(self, url: str, detail: str) -> None:
        super().__init__(f"Could not reach HEPData: {url}. {detail}")
        self.url = url
        self.detail = detail
