from stt_service.app import create_app
from stt_service.recognizer import WhisperRecognizer
from stt_service.settings import SttSettings

settings = SttSettings()
app = create_app(settings, load=lambda: WhisperRecognizer(settings))
