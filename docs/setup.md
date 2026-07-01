# Setup Guide

## Prerequisites

- Python 3.10+
- ffmpeg (for audio conversion)
- A DeepSeek API key ([platform.deepseek.com](https://platform.deepseek.com))

## 1. Install Dependencies

```bash
pip install funasr fastapi uvicorn httpx edge-tts
```

> `funasr` may require additional system packages. See [FunASR docs](https://github.com/modelscope/FunASR) if installation fails.

## 2. Download SenseVoice ASR Model

```bash
huggingface-cli download FunAudioLLM/SenseVoiceSmall --local-dir ./models/SenseVoiceSmall
```

Set the path as an environment variable:

```bash
export SENSEVOICE_MODEL_PATH=./models/SenseVoiceSmall
```

## 3. Configure DeepSeek API Key

Copy the example env file and add your key:

```bash
cp .env.example .env
# Edit .env and add: DEEPSEEK_API_KEY=sk-your-key-here
```

The server reads the key from:
1. `DEEPSEEK_API_KEY` environment variable
2. `.env` file in the project directory

## 4. Run the Server

```bash
python server.py
```

Opens at **http://localhost:8765**

### Optional: HTTPS

Generate a self-signed cert for local use:

```bash
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem \
  -days 365 -nodes -subj "/CN=localhost"
```

Place `cert.pem` and `key.pem` in the project root. The server will auto-detect them and enable HTTPS.

## Architecture

```
Browser (WebAudio API) ──WAV audio──▶ FastAPI Server
                                          │
                                    ┌─────┴─────┐
                                    │ SenseVoice │ (ASR)
                                    └─────┬─────┘
                                          │ text
                                    ┌─────┴─────┐
                                    │  DeepSeek  │ (LLM)
                                    └─────┬─────┘
                                          │ text
                                    ┌─────┴─────┐
                                    │  edge-tts  │ (TTS)
                                    └─────┬─────┘
                                          │ audio
Browser ◀───────────WAV audio─────────────┘
```

## Voice Demo

Supports Cantonese (廣東話) by default. Change the system prompt in `server.py` and the TTS voice in `text_to_speech()` for other dialects/languages.
