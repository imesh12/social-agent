from pathlib import Path

import edge_tts

from services.utils.logging import get_rotating_logger
from services.utils.retry import retry

voice_logger = get_rotating_logger("voice", "voice.log")


class TTSService:
    @retry(max_attempts=3, initial_delay=1, backoff_multiplier=3, logger=voice_logger)
    async def generate_audio(
        self,
        text: str,
        output_path: str,
        voice: str = "en-US-JennyNeural",
    ) -> None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(path))
