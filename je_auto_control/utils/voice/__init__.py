"""Voice-command router: map recognized phrases to AC_* action lists."""
from je_auto_control.utils.voice.voice_router import (
    VoiceCommand, VoiceRouter, default_voice_router,
)

__all__ = ["VoiceCommand", "VoiceRouter", "default_voice_router"]
