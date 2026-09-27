class KrEpgError(Exception):
    """Base exception for expected application failures."""


class ConfigurationError(KrEpgError):
    """Raised when configuration is missing or unsafe."""


class SourceError(KrEpgError):
    """Raised when an upstream source cannot be read safely."""


class FetchError(SourceError):
    """Raised after bounded retries against an upstream source fail."""


class ValidationError(KrEpgError):
    """Raised when generated output fails validation."""
