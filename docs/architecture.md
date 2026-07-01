# Architecture

## Flow

```
┌─────────────────────────────────────────────────────────────┐
│                      Browser (Frontend)                      │
│                                                              │
│  Web Audio API → ScriptProcessor → PCM Float32 → encodeWAV  │
│                                                              │
│  VAD (Voice Activity Detection):                             │
│    • calcRMS() per 4096-sample buffer                        │
│    • RMS > threshold → voice active                          │
│    • 600ms silence → utterance complete                      │
│    • Fire-and-forget: each utterance sent immediately        │
│      (no queue — multiple API calls run in parallel)         │
│                                                              │
│  Playback: AudioContext.decodeAudioData() → BufferSource     │
│    • Anti-echo: 300ms cooldown after playback starts         │
│    • Multiple responses can overlap                          │
└───────────────────────┬─────────────────────────────────────┘
                        │ POST /api/chat (multipart: audio WAV)
                        ▼
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI Server (Backend)                │
│                                                              │
│  1. ffmpeg resample → 16kHz mono S16 PCM                     │
│  2. SenseVoice ASR (funasr) → transcribed text               │
│  3. DeepSeek Chat API → Cantonese text response              │
│  4. edge-tts (zh-HK-WanLungNeural) → WAV audio              │
│                                                              │
│  API key: read from env var or .env file                     │
│  Model: SENSEVOICE_MODEL_PATH env var                        │
└─────────────────────────────────────────────────────────────┘
```

## Key Design Decisions

### Why AudioContext + ScriptProcessor instead of MediaRecorder?

MediaRecorder produces WebM/Opus containers that ffmpeg struggles to parse
(unknown-length EBML elements from Chrome). Recording raw PCM via
AudioContext and encoding WAV in-browser avoids this entirely —
the backend receives a proper WAV file every time.

### Why fire-and-forget instead of queueing?

Each utterance is sent to the backend immediately upon silence detection.
Multiple API calls run in parallel — utterance B can be processing via
DeepSeek while utterance A's TTS is still being generated. This eliminates
the sequential bottleneck of turn-based conversation.

### Why SenseVoice over Whisper?

SenseVoiceSmall runs ~170× realtime on CPU (~0.3s for 4s of audio)
and has excellent Cantonese recognition. Whisper is ~10× realtime on CPU
and doesn't support Cantonese as well out of the box.

### Why edge-tts?

Free, no API key needed, runs locally. zh-HK-WanLungNeural produces
natural Cantonese (香港粵語). Latency ~1.5-3s for typical responses.
