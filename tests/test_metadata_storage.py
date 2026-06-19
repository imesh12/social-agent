import json
from pathlib import Path

from services.metadata_service import GenerationMetadataService


def test_metadata_json_saved_correctly(tmp_path: Path) -> None:
    service = GenerationMetadataService(output_dir=str(tmp_path))
    metadata = {
        "timestamp": "2026-06-19T00:00:00+00:00",
        "topic": "AI Tools",
        "research": "AI tools are trending.",
        "script": "Hook: AI tools are changing fast.",
        "title": "Top 3 AI Tools You Need In 2026 #shorts",
        "description": "Discover AI tools changing productivity.",
        "tags": ["AI", "ChatGPT", "Technology"],
        "thumbnail_path": "storage/thumbnails/thumb_1.jpg",
        "video_path": "storage/videos/video_1.mp4",
        "youtube_id": "abc123",
    }

    path = service.save_metadata(metadata)

    assert path.exists()
    assert path.name.endswith(".json")
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved == metadata
