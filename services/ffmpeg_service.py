from pathlib import Path

import ffmpeg
import imageio_ffmpeg

from services.utils.logging import get_rotating_logger
from services.utils.retry import retry

video_logger = get_rotating_logger("video", "video.log")


class FFmpegService:
    @retry(max_attempts=3, initial_delay=1, backoff_multiplier=3, logger=video_logger)
    def create_video_from_image_and_audio(
        self,
        image_path: str,
        audio_path: str,
        output_path: str,
        width: int = 1080,
        height: int = 1920,
    ) -> None:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        video_input = ffmpeg.input(image_path, loop=1, framerate=30)
        audio_input = ffmpeg.input(audio_path)

        video = (
            video_input
            .filter("scale", width, height, force_original_aspect_ratio="increase")
            .filter("crop", width, height)
            .filter("format", "yuv420p")
        )

        (
            ffmpeg
            .output(
                video,
                audio_input.audio,
                str(output),
                vcodec="libx264",
                acodec="aac",
                shortest=None,
                movflags="+faststart",
            )
            .overwrite_output()
            .run(cmd=imageio_ffmpeg.get_ffmpeg_exe(), quiet=True)
        )
