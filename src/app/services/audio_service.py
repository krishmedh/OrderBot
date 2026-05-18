from app.domain.interfaces import SpeechToTextProvider


class AudioService:
    def __init__(self, stt_provider: SpeechToTextProvider) -> None:
        self.stt_provider = stt_provider

    def transcribe_customer_audio(self, audio_url: str) -> str:
        return self.stt_provider.transcribe(audio_url)
