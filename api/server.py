"""
FastAPI server for voice-enabled conductor agent.
Provides REST API and web interface for mobile access.
Supports Solo (Super Codex), standard, and Council-of-4 modes.
"""

import os
import sys
import uuid
from pathlib import Path

# Add conductor_agent directory to sys.path so bare internal imports work
_pkg_dir = str(Path(__file__).resolve().parent.parent)
if _pkg_dir not in sys.path:
    sys.path.insert(0, _pkg_dir)
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from conductor.agent import ConductorAgent
from voice.voice_processor import get_voice_processor
from utils.logger import logger
from config.settings import settings

# Initialize FastAPI app
app = FastAPI(
    title="Super Codex — Conductor Voice Agent",
    description=(
        "Voice-enabled AI assistant with persistent memory. "
        "Supports Solo (Super Codex), standard, and Council-of-4 modes."
    ),
    version="2.0.0",
)

# Add CORS middleware for mobile access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for mobile
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services (lazy initialization to avoid startup crashes)
conductor = None
_super_codex_instance = None
_council_instance = None
voice_processor = None


def _is_cloud() -> bool:
    """True on Cloud Run / Render / Railway / Heroku — skip ChromaDB."""
    return any(
        os.getenv(v)
        for v in ("K_SERVICE", "RENDER", "RAILWAY", "HEROKU")
    )



def get_conductor():
    """Lazy initialization of conductor agent."""
    global conductor
    if conductor is None:
        # Use minimal conductor in cloud environments (no ChromaDB)
        is_cloud = (
            os.getenv("K_SERVICE")  # Cloud Run
            or os.getenv("RENDER")
            or os.getenv("RAILWAY")
            or os.getenv("HEROKU")
        )

        try:
            if is_cloud:
                from conductor.minimal import MinimalConductor
                conductor = MinimalConductor()
                logger.info("Using minimal conductor (cloud mode - no memory)")
            else:
                conductor = ConductorAgent()
                logger.info("Using full conductor (local mode - with memory)")
        except Exception as e:
            logger.error(f"Failed to initialize conductor: {e}")
            # Ultimate fallback - minimal conductor
            try:
                from conductor.minimal import MinimalConductor
                conductor = MinimalConductor()
                logger.info("Fallback to minimal conductor due to error")
            except Exception:
                raise ValueError(f"Could not initialize any conductor: {e}")
    return conductor


def get_super_codex():
    """Lazy initialization of the Super Codex (solo OpenAI) conductor."""
    global _super_codex_instance
    if _super_codex_instance is None:
        from conductor.super_codex import SuperCodex
        _super_codex_instance = SuperCodex(model=settings.super_codex_model)
        base_conductor = get_conductor()
        _super_codex_instance.retriever = getattr(base_conductor, "retriever", None)
        _super_codex_instance.skill_manager = getattr(base_conductor, "skill_manager", None)
        _super_codex_instance.current_skill = getattr(base_conductor, "current_skill", None)
        logger.info(
            f"SuperCodex initialised (model={settings.super_codex_model})"
        )
    return _super_codex_instance


def get_council():
    """Lazy initialization of the Council of 4 conductor."""
    global _council_instance
    if _council_instance is None:
        from conductor.council import CouncilConductor
        _council_instance = CouncilConductor()
        base_conductor = get_conductor()
        shared_retriever = getattr(base_conductor, "retriever", None)
        _council_instance.retriever = shared_retriever
        _council_instance._lead.retriever = shared_retriever
        _council_instance._lead.skill_manager = getattr(base_conductor, "skill_manager", None)
        _council_instance._lead.current_skill = getattr(base_conductor, "current_skill", None)
        logger.info("CouncilConductor initialised")
    return _council_instance


def get_default_chat_agent():
    """Return the default agent for /api/chat based on configured mode."""
    mode = settings.conductor_mode.lower()
    if mode == "super_codex":
        return get_super_codex()
    if mode == "council":
        return get_council()
    return get_conductor()



def get_voice_processor_instance():
    """Lazy initialization of voice processor."""
    global voice_processor
    if voice_processor is None:
        voice_processor = get_voice_processor()
    return voice_processor


# Create temp directory for audio files
TEMP_DIR = Path("temp_audio")
TEMP_DIR.mkdir(exist_ok=True)


# Request/Response Models
class ChatRequest(BaseModel):
    query: str
    platform_filter: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    sources: list
    audio_url: Optional[str] = None


class CouncilMemberResponse(BaseModel):
    name: str
    provider: str
    response: Optional[str] = None
    error: Optional[str] = None


class CouncilChatResponse(BaseModel):
    response: str
    sources: list
    council: List[CouncilMemberResponse]
    members_used: int
    model: str


class VoiceSettings(BaseModel):
    voice: str = "nova"


# In-memory voice settings (could be persisted later)
current_voice_settings = VoiceSettings()


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main web interface."""
    static_dir = Path(__file__).parent / "static"
    index_file = static_dir / "index.html"

    if index_file.exists():
        with open(index_file, 'r', encoding='utf-8') as f:
            return f.read()
    return """
        <html>
            <body>
                <h1>Conductor Voice Agent</h1>
                <p>Web interface will be available soon.</p>
                <p>API is running. Try POST /api/chat</p>
            </body>
        </html>
        """


@app.on_event("startup")
async def _startup_log_config():
    """Log API-key configuration so missing keys are obvious in cloud logs."""
    providers = settings.configured_providers()
    if providers:
        logger.info(f"Configured LLM providers: {', '.join(providers)}")
    else:
        logger.warning(
            "No LLM API key configured. The /api/chat endpoint will fail "
            "until OPENAI_API_KEY (or another provider key) is set. "
            "See README -> Deploy."
        )


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    providers = settings.configured_providers()
    return {
        "status": "healthy",
        "service": "super-codex-conductor",
        "version": "2.0.0",
        "mode": "minimal" if _is_cloud() else "full",
        "conductor_mode": settings.conductor_mode,
        "providers": providers,
        "api_keys_configured": bool(providers),
        "super_codex_model": settings.super_codex_model,
    }


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Text-based chat endpoint.

    Args:
        request: Chat request with query and optional platform filter

    Returns:
        Chat response with answer and sources
    """
    try:
        logger.info(f"Chat request: {request.query[:100]}...")

        result = get_default_chat_agent().chat(
            query=request.query,
            platform_filter=request.platform_filter
        )

        return ChatResponse(
            response=result['response'],
            sources=result['sources']
        )

    except Exception as e:
        logger.error(f"Error in chat endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/super-codex", response_model=ChatResponse)
async def super_codex_chat(request: ChatRequest):
    """
    Super Codex Solo endpoint — uses OpenAI's best model (gpt-4o) exclusively.

    This is the ChatGPT-SOLO mode: a single powerful AI with no council.
    """
    try:
        logger.info(f"Super Codex request: {request.query[:100]}...")
        result = get_super_codex().chat(
            query=request.query,
            platform_filter=request.platform_filter,
        )
        return ChatResponse(
            response=result["response"],
            sources=result["sources"],
        )
    except Exception as exc:
        logger.error(f"Error in /api/super-codex: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/council", response_model=CouncilChatResponse)
async def council_chat(request: ChatRequest):
    """
    Council of 4 Super Conductor endpoint.

    Queries all available AI providers (OpenAI/Codex, Gemini, Grok, Claude)
    concurrently.  Super Codex (OpenAI) acts as Lead and synthesises the
    council responses into a single, authoritative answer.
    """
    try:
        logger.info(f"Council request: {request.query[:100]}...")
        result = get_council().chat(
            query=request.query,
            platform_filter=request.platform_filter,
        )
        council_members = [
            CouncilMemberResponse(**m) for m in result["council"]
        ]
        return CouncilChatResponse(
            response=result["response"],
            sources=result["sources"],
            council=council_members,
            members_used=result["members_used"],
            model=result["model"],
        )
    except Exception as exc:
        logger.error(f"Error in /api/council: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/council/status")
async def council_status():
    """
    Returns which council members are available (have API keys configured).
    """
    from conductor.council import _COUNCIL_MEMBERS
    members = []
    for name, provider, env_var, model in _COUNCIL_MEMBERS:
        key_set = bool(os.getenv(env_var, ""))
        members.append(
            {
                "name": name,
                "provider": provider,
                "model": model,
                "available": key_set,
                "role": "lead" if provider == "openai" else "member",
            }
        )
    return {
        "council": members,
        "members_available": sum(1 for m in members if m["available"]),
        "lead": "Codex/ChatGPT (OpenAI)",
    }


@app.post("/api/voice-chat")
async def voice_chat(audio: UploadFile = File(...)):
    """
    Voice-based chat endpoint.
    Accepts audio input, transcribes it, generates response, and returns audio.

    Args:
        audio: Audio file (webm, mp3, wav, etc.)

    Returns:
        JSON with transcription, response text, and URL to audio response
    """
    try:
        # Save uploaded audio temporarily
        audio_id = str(uuid.uuid4())
        input_path = TEMP_DIR / f"input_{audio_id}.webm"

        with open(input_path, "wb") as f:
            content = await audio.read()
            f.write(content)

        logger.info(f"Received audio file: {input_path}")

        # Transcribe audio to text
        vp = get_voice_processor_instance()
        transcription = await vp.transcribe_audio(input_path)
        logger.info(f"Transcription: {transcription}")

        # Get response from conductor
        result = get_conductor().chat(query=transcription)
        response_text = result['response']

        # Synthesize speech from response
        output_path = TEMP_DIR / f"output_{audio_id}.mp3"
        await vp.synthesize_speech(
            text=response_text,
            output_path=output_path,
            voice=current_voice_settings.voice
        )

        # Clean up input file
        input_path.unlink()

        return {
            "transcription": transcription,
            "response": response_text,
            "sources": result['sources'],
            "audio_url": f"/api/audio/{output_path.name}"
        }

    except Exception as e:
        logger.error(f"Error in voice chat endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/audio/{filename}")
async def get_audio(filename: str):
    """
    Serve generated audio file.

    Args:
        filename: Name of audio file

    Returns:
        Audio file
    """
    file_path = TEMP_DIR / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")

    return FileResponse(
        file_path,
        media_type="audio/mpeg",
        filename=filename
    )


@app.post("/api/transcribe")
async def transcribe(audio: UploadFile = File(...)):
    """
    Transcribe audio to text only.

    Args:
        audio: Audio file

    Returns:
        Transcribed text
    """
    try:
        # Save temporarily
        audio_id = str(uuid.uuid4())
        temp_path = TEMP_DIR / f"temp_{audio_id}.webm"

        with open(temp_path, "wb") as f:
            content = await audio.read()
            f.write(content)

        # Transcribe
        transcription = await get_voice_processor_instance().transcribe_audio(temp_path)

        # Clean up
        temp_path.unlink()

        return {"transcription": transcription}

    except Exception as e:
        logger.error(f"Error in transcribe endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/synthesize")
async def synthesize(text: str, voice: Optional[str] = None):
    """
    Synthesize speech from text.

    Args:
        text: Text to convert to speech
        voice: Optional voice to use

    Returns:
        URL to audio file
    """
    try:
        audio_id = str(uuid.uuid4())
        output_path = TEMP_DIR / f"synth_{audio_id}.mp3"

        await get_voice_processor_instance().synthesize_speech(
            text=text,
            output_path=output_path,
            voice=voice or current_voice_settings.voice
        )

        return {"audio_url": f"/api/audio/{output_path.name}"}

    except Exception as e:
        logger.error(f"Error in synthesize endpoint: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/voices")
async def get_voices():
    """Get available TTS voices."""
    return {"voices": get_voice_processor_instance().get_available_voices()}


@app.post("/api/settings/voice")
async def set_voice(settings: VoiceSettings):
    """Update voice settings."""
    current_voice_settings.voice = settings.voice
    return {"voice": current_voice_settings.voice}


@app.get("/api/settings/voice")
async def get_voice_settings():
    """Get current voice settings."""
    return {"voice": current_voice_settings.voice}


# Mount static files (will create later)
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8080))

    logger.info(f"Starting Conductor Voice Agent on port {port}")

    uvicorn.run(
        "api.server:app",
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
