from services.publisher.base_adapter import BasePublisherAdapter
from services.publisher.models import PublishRequest, PublishResult
from services.publisher.registry import PublisherRegistry


class PublisherService:
    """Platform-neutral publishing facade backed by a registry of adapters."""

    def __init__(self, registry: PublisherRegistry | None = None) -> None:
        self.registry = registry or PublisherRegistry()

    def register_adapter(self, adapter: BasePublisherAdapter) -> None:
        """Register a platform adapter."""
        self.registry.register(adapter)

    async def publish(self, platform_name: str, request: PublishRequest) -> PublishResult:
        """Publish content through the selected platform adapter."""
        return await self.registry.get(platform_name).publish(request)

    async def validate(self, platform_name: str) -> bool:
        """Validate the selected platform adapter connection."""
        return await self.registry.get(platform_name).validate()

    async def disconnect(self, platform_name: str) -> None:
        """Disconnect the selected platform adapter."""
        await self.registry.get(platform_name).disconnect()

    async def refresh(self, platform_name: str) -> bool:
        """Refresh credentials through the selected platform adapter."""
        return await self.registry.get(platform_name).refresh_credentials()
