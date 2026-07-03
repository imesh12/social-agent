from services.publisher.base_adapter import BasePublisherAdapter
from services.publisher.exceptions import PublisherError


class PublisherRegistry:
    """In-memory registry of platform publisher adapters."""

    def __init__(self) -> None:
        self._adapters: dict[str, BasePublisherAdapter] = {}

    def register(self, adapter: BasePublisherAdapter) -> None:
        """Register or replace an adapter by canonical platform name."""
        self._adapters[self._normalize(adapter.platform_name)] = adapter

    def unregister(self, platform_name: str) -> None:
        """Unregister an adapter by platform name."""
        key = self._normalize(platform_name)
        if key not in self._adapters:
            raise PublisherError(f"Publisher adapter is not registered: {platform_name}")
        del self._adapters[key]

    def get(self, platform_name: str) -> BasePublisherAdapter:
        """Return a registered adapter or raise when missing."""
        key = self._normalize(platform_name)
        try:
            return self._adapters[key]
        except KeyError as exc:
            raise PublisherError(f"Publisher adapter is not registered: {platform_name}") from exc

    def list_platforms(self) -> list[str]:
        """List registered platform names."""
        return sorted(adapter.platform_name for adapter in self._adapters.values())

    def _normalize(self, platform_name: str) -> str:
        return platform_name.strip().lower()
