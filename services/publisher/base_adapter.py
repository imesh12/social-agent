from abc import ABC, abstractmethod

from services.publisher.models import ChannelInfo, PublishRequest, PublishResult


class BasePublisherAdapter(ABC):
    """Asynchronous platform adapter contract for publishing integrations."""

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """Return the canonical platform name."""

    @abstractmethod
    async def connect(self) -> ChannelInfo:
        """Connect or return the active platform channel."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Disconnect the active platform channel."""

    @abstractmethod
    async def validate(self) -> bool:
        """Validate platform credentials and connection state."""

    @abstractmethod
    async def publish(self, request: PublishRequest) -> PublishResult:
        """Publish content to the platform."""

    @abstractmethod
    async def refresh_credentials(self) -> bool:
        """Refresh credentials when supported by the platform."""

    @abstractmethod
    async def supports_scheduling(self) -> bool:
        """Return whether the platform supports scheduled publishing."""
