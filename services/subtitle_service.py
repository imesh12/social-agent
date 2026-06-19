import re
from pathlib import Path


class SubtitleService:
    def generate_srt(
        self,
        script_text: str,
        output_path: str,
        seconds_per_block: int = 5,
    ) -> None:
        sentences = self._split_sentences(script_text)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        blocks = []
        for index, sentence in enumerate(sentences, start=1):
            start_seconds = (index - 1) * seconds_per_block
            end_seconds = index * seconds_per_block
            blocks.append(
                "\n".join(
                    [
                        str(index),
                        f"{self._format_timestamp(start_seconds)} --> {self._format_timestamp(end_seconds)}",
                        sentence,
                    ]
                )
            )

        path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")

    def _split_sentences(self, text: str) -> list[str]:
        cleaned = self._clean_script_text(text)
        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", cleaned) if part.strip()]
        return sentences or [cleaned]

    def _clean_script_text(self, text: str) -> str:
        without_labels = re.sub(r"\b(?:Hook|Body|Ending):", " ", text, flags=re.IGNORECASE)
        without_quotes = without_labels.replace('"', "")
        return re.sub(r"\s+", " ", without_quotes).strip()

    def _format_timestamp(self, total_seconds: int) -> str:
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02}:{minutes:02}:{seconds:02},000"
