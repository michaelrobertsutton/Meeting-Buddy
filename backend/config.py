from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AudioConfig:
    device_name: str = "BlackHole"
    sample_rate: int = 48000  # BlackHole native rate
    target_sample_rate: int = 16000  # Whisper requires 16kHz
    channels: int = 2  # BlackHole 2ch
    block_duration_ms: int = 100  # Frame size in ms
    queue_maxsize: int = 300  # ~30s buffer at 100ms/frame
    capture_binary: str = "audio-capture/.build/release/AudioCapture"

    @property
    def block_size(self) -> int:
        """Number of samples per frame at native sample rate."""
        return int(self.sample_rate * self.block_duration_ms / 1000)

    @property
    def target_block_size(self) -> int:
        """Number of samples per frame at target (16kHz) sample rate."""
        return int(self.target_sample_rate * self.block_duration_ms / 1000)


@dataclass
class VADConfig:
    threshold: float = 0.5
    use_onnx: bool = True


@dataclass
class ASRConfig:
    model_size: str = "small"
    device: str = "cpu"
    compute_type: str = "int8"
    language: str = "en"
    beam_size: int = 1
    no_speech_threshold: float = 0.95


@dataclass
class StreamingConfig:
    pre_speech_buffer_ms: int = 300  # Keep audio before speech starts
    silence_duration_ms: int = 300  # Silence to trigger end of speech
    min_chunk_duration_s: float = 0.3  # Skip very short chunks
    max_chunk_duration_s: float = 5.0  # Force transcription at this length


@dataclass
class ServerConfig:
    host: str = "localhost"
    port: int = 8765
    poll_interval_ms: int = 200  # How often to check for new segments


@dataclass
class TranscriptConfig:
    max_age_s: float = 120.0  # Keep last 120s of transcript


@dataclass
class ActiveQuestionConfig:
    lookback_window_s: float = 60.0  # How far back to scan for questions
    debounce_interval_s: float = 1.0  # Min time between question changes
    min_confidence: float = 0.3  # Minimum score to surface a question
    manual_override_timeout_s: float = 90.0  # Auto-resume after manual override
    question_staleness_s: float = 30.0  # Questions older than this are considered stale
    track_top_n: int = 3  # Track top N questions, not just the best one


@dataclass
class IngestRuntimeConfig:
    project_name: str | None = None  # Active project; None = no RAG
    base_path: str = "~/.meeting-buddy/projects"


@dataclass
class SynthesisConfig:
    model: str = "gpt-4o-mini"
    temperature: float = 0.2
    max_tokens: int = 1500
    enabled: bool = True


@dataclass
class AppConfig:
    audio: AudioConfig = field(default_factory=AudioConfig)
    vad: VADConfig = field(default_factory=VADConfig)
    asr: ASRConfig = field(default_factory=ASRConfig)
    streaming: StreamingConfig = field(default_factory=StreamingConfig)
    server: ServerConfig = field(default_factory=ServerConfig)
    transcript: TranscriptConfig = field(default_factory=TranscriptConfig)
    question: ActiveQuestionConfig = field(default_factory=ActiveQuestionConfig)
    ingest: IngestRuntimeConfig = field(default_factory=IngestRuntimeConfig)
    synthesis: SynthesisConfig = field(default_factory=SynthesisConfig)
