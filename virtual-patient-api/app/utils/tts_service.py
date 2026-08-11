"""
Text-to-Speech Service
Handles Azure OpenAI TTS API integration for generating audio from text.
"""

import os
import tempfile
import requests
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


class TTSService:
    """Service for generating audio from text using Azure OpenAI TTS."""
    
    # Voice mapping: personality_namespace_key -> {male: voice, female: voice}
    # Azure TTS voices: alloy, echo, fable, onyx, nova, shimmer
    PERSONALITY_VOICES = {
        "elderly_forgetful": {
            "male": "onyx",      # Older, neutral-sounding
            "female": "echo"       # Softer, older-sounding
        },
        "know_it_all": {
            "male": "onyx",       # Confident, authoritative
            "female": "nova"    # Clear, assertive
        },
        "rude_unfriendly": {
            "male": "onyx",       # Harsher, deeper
            "female": "alloy"      # Sharp, less friendly
        },
        "friendly_polite": {
            "male": "onyx",      # Warm, friendly
            "female": "nova"   # Pleasant, warm
        },
        "confused_inquisitive": {
            "male": "onyx",       # Uncertain, questioning tone
            "female": "nova"      # Soft, questioning
        },
        "skeptical_spiritual": {
            "male": "echo",       # Deep, thoughtful
            "female": "shimmer"   # Mysterious, thoughtful
        }
    }
    
    # Default voices if personality or gender not found
    DEFAULT_VOICES = {
        "male": "alloy",
        "female": "shimmer"
    }
    
    def __init__(self):
        # Get environment variables
        # Try AZURE_API_KEY first (as per documentation), fallback to AZURE_OPENAI_API_KEY
        api_key_raw = os.getenv("AZURE_API_KEY") or os.getenv("AZURE_OPENAI_API_KEY")
        endpoint_base_raw = os.getenv("AZURE_OPENAI_ENDPOINT", "https://invuniandesai-2.openai.azure.com")
        
        # Strip quotes from environment variables (common issue with .env files)
        self.api_key = api_key_raw.strip('"\'') if api_key_raw else None
        self.endpoint_base = endpoint_base_raw.strip('"\'') if endpoint_base_raw else None
        
        self.deployment_name = "gpt-4o-mini-tts"
        
        # Clean endpoint URL
        if self.endpoint_base and self.endpoint_base.endswith("/"):
            self.endpoint_base = self.endpoint_base.rstrip("/")
        
        # Construct the TTS endpoint URL
        self.tts_url = f"{self.endpoint_base}/openai/deployments/{self.deployment_name}/audio/speech"
        
        # TTS API versions to try (in order of preference)
        # TTS requires specific API versions, different from chat completions
        self.api_versions_to_try = [
            "2025-03-01-preview",  # Primary version for TTS (from documentation)
            "2024-08-01-preview",  # Fallback versions
            "2024-09-01-preview",
            "2024-10-01-preview",
            os.getenv("AZURE_OPENAI_API_VERSION"),  # User's configured version (may not work for TTS)
        ]
        # Remove None values and duplicates
        seen = set()
        self.api_versions_to_try = [
            v for v in self.api_versions_to_try 
            if v and not (v in seen or seen.add(v))
        ]
    
    @classmethod
    def get_voice_for_personality(cls, personality_namespace_key: Optional[str] = None, gender: Optional[str] = None) -> str:
        """
        Get the appropriate TTS voice based on personality and gender.
        
        Args:
            personality_namespace_key: The namespace_key of the personality (e.g., "friendly_polite")
            gender: Patient gender ("male" or "female")
            
        Returns:
            Azure TTS voice name
        """
        # Normalize gender
        gender_normalized = gender.lower() if gender else None
        
        # If we have both personality and gender, try to get specific voice
        if personality_namespace_key and gender_normalized:
            personality_voices = cls.PERSONALITY_VOICES.get(personality_namespace_key)
            if personality_voices:
                voice = personality_voices.get(gender_normalized)
                if voice:
                    print(f"🎭 Selected voice '{voice}' for personality '{personality_namespace_key}' ({gender_normalized})")
                    return voice
        
        # Fallback to default based on gender
        if gender_normalized:
            voice = cls.DEFAULT_VOICES.get(gender_normalized, "alloy")
            print(f"🎭 Using default voice '{voice}' for gender '{gender_normalized}'")
            return voice
        
        # Ultimate fallback
        print(f"🎭 Using default voice 'alloy' (no personality/gender specified)")
        return "alloy"
    
    def generate_audio(
        self,
        text: str,
        voice: Optional[str] = None,
        personality_namespace_key: Optional[str] = None,
        gender: Optional[str] = None,
        output_file: Optional[str] = None
    ) -> Optional[bytes]:
        """
        Generate audio from text using Azure OpenAI TTS.
        
        Args:
            text: The text to convert to speech
            voice: The voice to use. If None, will be selected based on personality and gender.
            personality_namespace_key: The namespace_key of the personality (e.g., "friendly_polite")
            gender: Patient gender ("male" or "female")
            output_file: Optional path to save the audio file. If None, returns bytes only.
            
        Returns:
            Audio data as bytes, or None if generation failed
        """
        # Determine voice if not explicitly provided
        if voice is None:
            voice = self.get_voice_for_personality(personality_namespace_key, gender)
        
        if not self.api_key:
            print("❌ TTS Service: API key not found in environment variables")
            return None
        
        if not text or not text.strip():
            print("⚠️  TTS Service: Empty text provided")
            return None

        # Prepare the request payload
        payload = {
            "model": self.deployment_name,
            "input": text,
            "voice": voice
        }
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        # Try different API versions until one works
        print(f"🔊 Generating TTS audio for text: '{text[:50]}...'")
        
        for api_version in self.api_versions_to_try:
            params = {"api-version": api_version}
            
            try:
                response = requests.post(
                    self.tts_url,
                    params=params,
                    headers=headers,
                    json=payload,
                    timeout=30
                )
                
                if response.status_code == 200:
                    audio_data = response.content
                    print(f"✅ TTS audio generated successfully ({len(audio_data):,} bytes) with API version: {api_version}")
                    
                    # Optionally save to file
                    if output_file:
                        with open(output_file, "wb") as f:
                            f.write(audio_data)
                        print(f"💾 Audio saved to: {output_file}")
                    
                    return audio_data
                elif response.status_code == 404:
                    # 404 means this API version doesn't work, try next one
                    print(f"⚠️  API version {api_version} returned 404, trying next version...")
                    continue
                else:
                    # Other errors might be auth issues, stop trying
                    print(f"❌ TTS request failed: {response.status_code} with API version: {api_version}")
                    try:
                        error_json = response.json()
                        error_msg = error_json.get('error', {}).get('message', 'Unknown error')
                        print(f"   Error: {error_msg}")
                    except:
                        print(f"   Response: {response.text[:200]}")
                    
                    # If it's not a 404, don't try other versions (likely auth issue)
                    if response.status_code not in [404]:
                        return None
                    continue
                    
            except requests.exceptions.RequestException as e:
                print(f"⚠️  Request exception with API version {api_version}: {e}")
                # Continue to next version
                continue
        
        # If we've tried all versions and none worked
        print(f"❌ All API versions failed for TTS endpoint")
        print(f"   Tried: {', '.join(self.api_versions_to_try)}")
        return None
    
    def generate_audio_to_file(
        self, 
        text: str, 
        voice: Optional[str] = None,
        personality_namespace_key: Optional[str] = None,
        gender: Optional[str] = None
    ) -> Optional[str]:
        """
        Generate audio and save to a temporary file.
        
        Args:
            text: The text to convert to speech
            voice: The voice to use. If None, will be selected based on personality and gender.
            personality_namespace_key: The namespace_key of the personality
            gender: Patient gender ("male" or "female")
            
        Returns:
            Path to the temporary audio file, or None if generation failed
        """
        # Create a temporary file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
        temp_file_path = temp_file.name
        temp_file.close()
        
        audio_data = self.generate_audio(
            text, 
            voice=voice,
            personality_namespace_key=personality_namespace_key,
            gender=gender,
            output_file=temp_file_path
        )
        
        if audio_data:
            return temp_file_path
        else:
            # Clean up temp file if generation failed
            try:
                os.unlink(temp_file_path)
            except:
                pass
            return None

