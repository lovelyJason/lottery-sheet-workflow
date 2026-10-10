"""Authentication failures that are safe to recover with a full login."""


AUTH_EXPIRED_CODES = {4001, 4002, 401, 403}


class SessionExpiredError(ValueError):
    """The server explicitly rejected the current authentication state."""

