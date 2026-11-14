"""Shared identities for the existing Whisper checkpoints (keep old keys)."""
from pathlib import Path

from .checkpoints import signature
from .media import executable
from .runtime import resolve_model


def tool_stamp(name):
    file=Path(executable(name)).resolve();stat=file.stat()
    return [str(file),stat.st_size,stat.st_mtime_ns]


def audio_key(source_id,media,track,options,ffmpeg_stamp,external=None):
    if external:
        return signature(['external-wav-v1',external['source_id'],options.external_offset,options.batch_seconds,ffmpeg_stamp,media.duration])
    return signature(['audio-wav-v2',source_id,track,options.batch_seconds,ffmpeg_stamp,media.origin,media.duration])


def speech_key(audio,model,external=None):
    resolved=Path(resolve_model(model));weights=resolved/'model.bin'
    stamp=[str(resolved),weights.stat().st_size,weights.stat().st_mtime_ns] if weights.is_file() else model
    return signature(['speech-v4-real-coverage' if external else 'speech-v2',audio,stamp,'faster-whisper-1.2.1','pt','word_timestamps'])
