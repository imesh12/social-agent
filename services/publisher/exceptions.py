class PublisherError(Exception):
    """Base exception for publisher framework failures."""


class AuthenticationError(PublisherError):
    """Raised when a platform connection is missing or invalid."""


class UploadError(PublisherError):
    """Raised when a platform upload fails."""


class RetryableUploadError(UploadError):
    """Raised when a platform upload failure can be retried."""


class QuotaExceededError(UploadError):
    """Raised when a platform quota limit prevents publishing."""


class PlatformConfigurationError(PublisherError):
    """Raised when a platform adapter is not configured correctly."""


class PlatformUnavailableError(PublisherError):
    """Raised when a platform is temporarily unavailable."""
