from dataclasses import dataclass

import pytest

from services.publisher import (
    BasePublisherAdapter,
    ChannelInfo,
    PublishMetadata,
    PublishRequest,
    PublishResult,
    PublisherError,
    PublisherRegistry,
    PublisherService,
)


@dataclass
class CallLog:
    publish_called: bool = False
    validate_called: bool = False
    disconnect_called: bool = False
    refresh_called: bool = False


class FakePublisherAdapter(BasePublisherAdapter):
    def __init__(self, platform: str = "Fake") -> None:
        self.platform = platform
        self.calls = CallLog()

    @property
    def platform_name(self) -> str:
        return self.platform

    async def connect(self) -> ChannelInfo:
        return ChannelInfo(platform=self.platform_name, channel_id="C1", channel_name="Fake Channel")

    async def disconnect(self) -> None:
        self.calls.disconnect_called = True

    async def validate(self) -> bool:
        self.calls.validate_called = True
        return True

    async def publish(self, request: PublishRequest) -> PublishResult:
        self.calls.publish_called = True
        return PublishResult(
            success=True,
            platform=self.platform_name,
            platform_video_id="video-1",
            video_url="https://example.test/video-1",
            processing_status="uploaded",
        )

    async def refresh_credentials(self) -> bool:
        self.calls.refresh_called = True
        return True

    async def supports_scheduling(self) -> bool:
        return False


def test_registry_registers_and_lists_adapters() -> None:
    registry = PublisherRegistry()
    adapter = FakePublisherAdapter(platform="Fake")

    registry.register(adapter)

    assert registry.get("fake") is adapter
    assert registry.list_platforms() == ["Fake"]


def test_registry_missing_adapter_raises_publisher_error() -> None:
    registry = PublisherRegistry()

    with pytest.raises(PublisherError):
        registry.get("Missing")


@pytest.mark.anyio
async def test_publisher_service_delegates_to_adapter() -> None:
    adapter = FakePublisherAdapter()
    service = PublisherService()
    service.register_adapter(adapter)

    request = PublishRequest(
        video_path="storage/videos/video.mp4",
        metadata=PublishMetadata(title="Title", description="Description", tags=["AI"]),
    )
    result = await service.publish("Fake", request)
    valid = await service.validate("Fake")
    refreshed = await service.refresh("Fake")
    await service.disconnect("Fake")

    assert result.success is True
    assert result.platform_video_id == "video-1"
    assert valid is True
    assert refreshed is True
    assert adapter.calls.publish_called is True
    assert adapter.calls.validate_called is True
    assert adapter.calls.refresh_called is True
    assert adapter.calls.disconnect_called is True
