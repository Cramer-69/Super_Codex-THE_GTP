"""
Voice processing with OpenAI Whisper (speech-to-text) and TTS (text-to-speech).
"""

import os
from pathlib import Path
from typing import Optional
from openai import OpenAI
from config.settings import settings
from utils.logger import logger


class VoiceProcessor:
    """Handles speech-to-text and text-to-speech using OpenAI APIs."""
    
    def __init__(self):
        """Initialize voice processor with OpenAI client."""
        if not settings.openai_api_key:
            raise ValueError("OpenAI API key is required for voice processing")
        
        self.client = OpenAI(api_key=settings.openai_api_key)
        self.whisper_model = "whisper-1"
        self.tts_model = "tts-1"
        self.tts_voice = "nova"  # Clear female voice
        
        logger.info("Initialized voice processor")
    
    async def transcribe_audio(self, audio_file_path: Path) -> str:
        """
        Transcribe audio file to text using Whisper.
        
        Args:
            audio_file_path: Path to audio file (mp3, mp4, mpeg, mpga, m4a, wav, webm)
            
        Returns:
            Transcribed text
        """
        try:
            logger.info(f"Transcribing audio file: {audio_file_path}")
            
            with open(audio_file_path, "rb") as audio_file:
                transcript = self.client.audio.transcriptions.create(
                    model=self.whisper_model,
                    file=audio_file,
                    response_format="text"
                )
            
            logger.info(f"Transcription complete: {transcript[:100]}...")
            return transcript
            
        except Exception as e:
            logger.error(f"Error transcribing audio: {e}")
            raise
    
    async def synthesize_speech(
        self,
        text: str,
        output_path: Optional[Path] = None,
        voice: Optional[str] = None
    ) -> Path:
        """
        Synthesize speech from text using TTS.
        
        Args:
            text: Text to convert to speech
            output_path: Optional path to save audio file
            voice: Voice to use (alloy, echo, fable, onyx, nova, shimmer)
            
        Returns:
            Path to generated audio file
        """
        try:
            voice = voice or self.tts_voice
            
            if not output_path:
                output_path = Path("temp_audio.mp3")
            
            logger.info(f"Synthesizing speech with voice '{voice}': {text[:100]}...")
            
            response = self.client.audio.speech.create(
                model=self.tts_model,
                voice=voice,
                input=text,
                response_format="mp3"
            )
            
            # Save audio to file
            response.stream_to_file(str(output_path))
            
            logger.info(f"Speech synthesis complete: {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Error synthesizing speech: {e}")
            raise
    
    def get_available_voices(self) -> list:
        """Get list of available TTS voices."""
        return [
            {
                "id": "alloy",
                "name": "Alloy",
                "description": "Neutral, versatile"
            },
            {
                "id": "echo",
                "name": "Echo",
                "description": "Male, clear"
            },
            {
                "id": "fable",
                "name": "Fable",
                "description": "British accent, expressive"
            },
            {
                "id": "onyx",
                "name": "Onyx",
                "description": "Deep, authoritative male"
            },
            {
                "id": "nova",
                "name": "Nova",
                "description": "Female, clear, professional"
            },
            {
                "id": "shimmer",
                "name": "Shimmer",
                "description": "Soft female, warm"
            }
        ]


# Singleton instance
voice_processor = None

def get_voice_processor() -> VoiceProcessor:
    """Get or create voice processor instance."""
    global voice_processor
    if voice_processor is None:
        voice_processor = VoiceProcessor()
    return voice_processor


if __name__ == "__main__":
    import asyncio
    
    async def test():
        processor = VoiceProcessor()
        
        # Test voices
        voices = processor.get_available_voices()
        print("Available voices:")
        for voice in voices:
            print(f"  - {voice['name']} ({voice['id']}): {voice['description']}")
        
        # Test TTS
        text = "Hello! I'm your voice conductor agent. I remember all your conversations and I'm here to help."
        audio_path = await processor.synthesize_speech(text)
        print(f"\nGenerated audio: {audio_path}")
    
    asyncio.run(test())
