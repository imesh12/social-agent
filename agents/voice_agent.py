import logging

from sqlalchemy.orm import Session

from database.models import Audio, AudioStatus, Script
from services.tts_service import TTSService

logger = logging.getLogger(__name__)


class ScriptNotFoundError(Exception):
    def __init__(self, script_id: int) -> None:
        super().__init__(f"Script {script_id} was not found")
        self.script_id = script_id


class VoiceAgent:
    def __init__(self, db: Session, tts_service: TTSService) -> None:
        self.db = db
        self.tts_service = tts_service

    async def generate_audio(
        self,
        script_id: int,
        voice: str = "en-US-JennyNeural",
    ) -> Audio:
        script = self.db.get(Script, script_id)
        if script is None:
            logger.warning("Cannot generate audio because script_id=%s was not found", script_id)
            raise ScriptNotFoundError(script_id)

        output_path = f"storage/audio/audio_{script.id}.mp3"
        logger.info("Generating audio for script_id=%s voice=%s", script.id, voice)

        try:
            await self.tts_service.generate_audio(
                text=script.content,
                output_path=output_path,
                voice=voice,
            )
            audio = Audio(script_id=script.id, path=output_path, status=AudioStatus.GENERATED)
            self.db.add(audio)
            self.db.commit()
            self.db.refresh(audio)
            logger.info("Generated audio id=%s script_id=%s path=%s", audio.id, script.id, audio.path)
            return audio
        except Exception:
            self.db.rollback()
            logger.exception("Audio generation failed for script_id=%s", script.id)
            raise
