# Web STT + LLM Voice Chat

A real-time voice chat web app with **continuous listening** (not push-to-talk, not turn-based). Speak Cantonese, get Cantonese voice responses — mic stays open, utterances are sent to the LLM in parallel, and multiple responses can overlap.

**Live demo:** Open the HTML page → tap "開始對話" → just start talking.

## Features

- 🎤 **Always-on mic** — no buttons to hold, no wake word needed
- ⚡ **Parallel API calls** — speak freely while AI processes previous utterances
- 🗣️ **Cantonese voice** — SenseVoice ASR + DeepSeek + edge-tts (zh-HK)
- 🔄 **Fire-and-forget** — silence detection (600ms) triggers immediate send
- 📱 **Mobile-friendly** — works in any modern browser
- 🔒 **API key on server** — key never touches the frontend

## Quick Start

```bash
# Install dependencies
pip install funasr fastapi uvicorn httpx edge-tts

# Download SenseVoice model
huggingface-cli download FunAudioLLM/SenseVoiceSmall --local-dir ./models/SenseVoiceSmall

# Set env vars
export SENSEVOICE_MODEL_PATH=./models/SenseVoiceSmall
export DEEPSEEK_API_KEY=***# Run
python server.py
```

Open **http://localhost:8765** in your browser.

> Full setup guide: [docs/setup.md](docs/setup.md)

## Architecture

```
Browser (WebAudio) ──WAV──▶ FastAPI ──▶ SenseVoice ASR ──▶ DeepSeek ──▶ edge-tts ──▶ Browser
     ▲                                                                                      │
     └────────────────────────────── WAV audio response ────────────────────────────────────┘
```

Multiple utterances run in parallel — no queue, no blocking.

## Project Structure

```
web-stt-llm/
├── server.py              # FastAPI backend (ASR + LLM + TTS)
├── .env.example           # Template for API keys
├── .gitignore
├── static/
│   └── index.html         # Frontend (WebAudio + VAD + playback)
├── docs/
│   ├── setup.md           # Detailed setup instructions
│   └── architecture.md    # Design decisions and flow
└── models/                # (create this, gitignored)
    └── SenseVoiceSmall/   # Download via huggingface-cli
```

## Tech Stack

| Component | Technology |
|---|---|
| ASR | SenseVoiceSmall (funasr, CPU, ~170× realtime) |
| LLM | DeepSeek Chat API (v4 flash) |
| TTS | edge-tts (zh-HK-WanLungNeural, free) |
| Server | FastAPI + uvicorn |
| Frontend | Web Audio API (raw PCM → browser WAV encoder) |
| VAD | Client-side RMS threshold (600ms silence timeout) |

## Why not turn-based?

Traditional voice assistants work in strict turns: you speak → they listen → they respond → they wait. This project removes that bottleneck. The mic never stops. Each utterance is dispatched immediately upon silence detection. The LLM API handles concurrency — you get responses back as fast as the model can generate them, not as fast as your turn would come in a queue.

## License

MIT
