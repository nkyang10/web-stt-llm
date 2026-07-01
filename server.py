"""
Cantonese Voice Chat Server
Architecture: Frontend (push-to-talk) → Backend (ASR → DeepSeek → TTS) → Response
API key stays on server — never exposed to frontend.
"""

import os
import json
import time
import asyncio
import tempfile
import subprocess
from pathlib import Path
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
import uvicorn

# ─── Config ─────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
AUDIO_DIR = STATIC_DIR / "responses"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"

# Try multiple ways to find the API key
def _find_api_key() -> str:
    """Try env var, .env file, then Hermes config."""
    # 1. Environment variable
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if key:
        return key

    # 2. .env file in project directory
    dotenv_path = BASE_DIR / ".env"
    if dotenv_path.exists():
        for line in dotenv_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("DEEPSEEK_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
                if key:
                    return key

    return ""

DEEPSEEK_API_KEY = _find_api_key()

# ─── ASR Engine (SenseVoice) ────────────────────────────────────────────────
asr_model = None

def get_asr():
    global asr_model
    if asr_model is None:
        print("[ASR] Loading SenseVoice model...")
        t0 = time.time()
        from funasr import AutoModel
        # Model path: set SENSEVOICE_MODEL_PATH env var to local model dir
        # Download from HuggingFace: FunAudioLLM/SenseVoiceSmall
        model_path = os.environ.get("SENSEVOICE_MODEL_PATH")
        if not model_path:
            raise RuntimeError(
                "SenseVoice model not configured. "
                "Set SENSEVOICE_MODEL_PATH to the local model directory. "
                "Download: huggingface-cli download FunAudioLLM/SenseVoiceSmall"
            )
        asr_model = AutoModel(
            model=model_path,
            trust_remote_code=True,
            vad_model="fsmn-vad",
            vad_kwargs={"max_single_segment_time": 30000},
            device="cpu",
        )
        print(f"[ASR] Loaded in {time.time()-t0:.1f}s ✅")
    return asr_model

def transcribe(audio_path: str) -> str:
    """Run ASR on audio file, return transcribed text."""
    model = get_asr()
    res = model.generate(
        input=audio_path,
        language="auto",   # auto-detects Cantonese / Chinese
        use_itn=True,      # inverse text normalization
    )
    from funasr.utils.postprocess_utils import rich_transcription_postprocess
    text = rich_transcription_postprocess(res[0]["text"])
    return text.strip()

# ─── DeepSeek API ───────────────────────────────────────────────────────────
async def ask_deepseek(user_text: str) -> str:
    """Send text to DeepSeek, get Cantonese response."""
    if not DEEPSEEK_API_KEY:
        return "⚠️ DeepSeek API key 未設定，請 check config.yaml"

    import httpx

    system_prompt = """你係一個好友善嘅廣東話對話AI助手。
你必須用廣東話（香港粵語）回答。
要自然、口語化、好似同朋友傾偈咁。
答案要簡潔，唔好太長。
唔好用書面語或者普通話。"""

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            DEEPSEEK_API_URL,
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_text},
                ],
                "temperature": 0.7,
                "max_tokens": 1024,
            },
        )
        if resp.status_code != 200:
            return f"⚠️ DeepSeek API error: {resp.status_code} - {resp.text[:200]}"

        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()

# ─── TTS (edge-tts) ─────────────────────────────────────────────────────────
async def text_to_speech(text: str, filename: str) -> str:
    """Generate Cantonese TTS audio file. Returns file path."""
    # Strip markdown / emoji for cleaner TTS
    import re
    clean = re.sub(r'[#*`\[\]()]', '', text)
    clean = re.sub(r'[\U0001F300-\U0001FFFF\U00020000-\U0002FFFF]', '', clean)

    out_path = AUDIO_DIR / filename
    cmd = [
        "edge-tts",
        "--voice", "zh-HK-WanLungNeural",
        "--text", clean,
        "--write-media", str(out_path),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    await proc.communicate()
    return str(out_path)

# ─── FastAPI App ─────────────────────────────────────────────────────────────
app = FastAPI(title="Cantonese Voice Chat")

@app.get("/")
async def root():
    """Serve the frontend HTML."""
    html_path = STATIC_DIR / "index.html"
    if not html_path.exists():
        return HTMLResponse("<h1>Frontend not built yet</h1>", status_code=503)
    return HTMLResponse(html_path.read_text(encoding="utf-8"))

@app.get("/audio/{filename}")
async def get_audio(filename: str):
    """Serve response audio files."""
    filepath = AUDIO_DIR / filename
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Audio not found")
    return FileResponse(str(filepath), media_type="audio/wav")

@app.post("/api/chat")
async def chat(audio: UploadFile = File(...)):
    """
    Main API: receive audio → ASR → DeepSeek → TTS → return response.
    """
    # Save uploaded audio
    suf = Path(audio.filename or "input.webm").suffix or ".webm"
    with tempfile.NamedTemporaryFile(suffix=suf, delete=False) as tmp:
        tmp.write(await audio.read())
        input_path = tmp.name

    # Convert to 16kHz mono WAV (FunASR needs proper WAV format)
    import subprocess
    wav_path = input_path + ".wav"
    convert_cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-ar", "16000", "-ac", "1",
        "-sample_fmt", "s16",
        wav_path
    ]
    conv = subprocess.run(convert_cmd, capture_output=True, text=True, timeout=30)
    if conv.returncode != 0:
        # If ffmpeg fails, try treating as raw PCM data
        try:
            with open(input_path, "rb") as f:
                raw = f.read()
            import struct
            # Try to read as raw PCM and create proper 16kHz WAV
            # This is a fallback - if format is wrong, raise error
            for p in [input_path, wav_path]:
                try: os.unlink(p)
                except: pass
            raise HTTPException(status_code=400,
                detail=f"音訊格式錯誤，請用 Chrome 開 chrome://flags/#unsafely-treat-insecure-origin-as-secure 加入網址")
        except HTTPException:
            raise
        except Exception:
            for p in [input_path, wav_path]:
                try: os.unlink(p)
                except: pass
            raise HTTPException(status_code=400, detail="音訊轉換失敗")

    try:
        # 1. ASR (use converted WAV)
        t0 = time.time()
        user_text = transcribe(wav_path)
        print(f"[ASR] '{user_text}' ({time.time()-t0:.2f}s)")

        if not user_text:
            return {
                "transcribed": "",
                "response": "我聽唔到你講嘢，可唔可以再講多次？",
                "audio_url": "",
            }

        # 2. DeepSeek
        t0 = time.time()
        ai_text = await ask_deepseek(user_text)
        print(f"[DeepSeek] '{ai_text[:80]}...' ({time.time()-t0:.2f}s)")

        # 3. TTS
        t0 = time.time()
        audio_filename = f"resp_{int(time.time())}.wav"
        audio_path = await text_to_speech(ai_text, audio_filename)
        audio_dur = _get_audio_duration(audio_path)
        print(f"[TTS] {audio_filename} ({audio_dur:.1f}s, gen in {time.time()-t0:.2f}s)")

        return {
            "transcribed": user_text,
            "response": ai_text,
            "audio_url": f"/audio/{audio_filename}",
            "audio_duration": audio_dur,
        }

    finally:
        # Cleanup input files
        for p in [input_path, wav_path]:
            try:
                os.unlink(p)
            except:
                pass

@app.post("/api/health")
async def health():
    """Check if model is loaded and ready."""
    try:
        _ = get_asr()
        return {"status": "ok", "model": "loaded"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def _get_audio_duration(path: str) -> float:
    """Get WAV duration via ffprobe."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=5,
        )
        return float(r.stdout.strip() or 1)
    except:
        return 1.0


# ─── Entrypoint ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8765))
    cert_file = BASE_DIR / "cert.pem"
    key_file = BASE_DIR / "key.pem"
    ssl_enabled = cert_file.exists() and key_file.exists()

    if ssl_enabled:
        print(f"   🔒 HTTPS enabled on port {port}")
        print(f"   🔓 HTTP also available on port {port}")
    else:
        print(f"   🔓 http://0.0.0.0:{port}")

    print(f"   Press Ctrl+C to stop\n")

    # Pre-warm model
    print("Pre-warming ASR model...")
    get_asr()
    print("Ready ✅\n")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        ssl_certfile=str(cert_file) if ssl_enabled else None,
        ssl_keyfile=str(key_file) if ssl_enabled else None,
    )
