# app.py
import streamlit as st
import PyPDF2
from elevenlabs import generate, voices, set_api_key, Voice
import os
from pathlib import Path
import tempfile
from datetime import datetime
import time
import json
from typing import List
import logging
import traceback

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Page config and styling
st.set_page_config(
    page_title="PDF to Audio Converter",
    page_icon="🎧",
    layout="wide"
)

# Custom CSS
st.markdown("""
    <style>
    .stAlert {
        max-width: 100%;
    }
    .main {
        padding: 2rem;
    }
    .uploadedFile {
        margin: 1rem 0;
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #f0f2f6;
    }
    </style>
""", unsafe_allow_html=True)

class RateLimit:
    def __init__(self, max_requests: int, time_window: int):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = []

    def is_allowed(self) -> bool:
        now = datetime.now().timestamp()
        self.requests = [req for req in self.requests 
                        if now - req < self.time_window]
        
        if len(self.requests) >= self.max_requests:
            return False
            
        self.requests.append(now)
        return True

class PDFAudioReader:
    def __init__(self, api_key: str):
        """Initialize the PDF to Audio converter."""
        self.api_key = api_key
        set_api_key(api_key)
        self.rate_limiter = RateLimit(max_requests=10, time_window=3600)  # 10 requests per hour
        
    @staticmethod
    def validate_pdf(file) -> bool:
        """Validate PDF file."""
        try:
            PyPDF2.PdfReader(file)
            return True
        except:
            return False
            
    def extract_text_from_pdf(self, pdf_file) -> str:
        """Extract text from a PDF file object."""
        try:
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            text = ""
            total_pages = len(pdf_reader.pages)
            
            # Add progress bar for text extraction
            progress_text = st.empty()
            progress_bar = st.progress(0)
            
            for i, page in enumerate(pdf_reader.pages):
                text += page.extract_text() + "\n"
                progress_bar.progress((i + 1) / total_pages)
                progress_text.text(f"Extracting text: page {i + 1}/{total_pages}")
                
            progress_text.empty()
            progress_bar.empty()
            
            return text
        except Exception as e:
            logger.error(f"PDF extraction error: {str(e)}\n{traceback.format_exc()}")
            raise Exception("Error reading PDF. Please ensure it's a valid PDF file.")
    
    def chunk_text(self, text: str, max_chars: int = 2000) -> List[str]:
        """Split text into smaller chunks."""
        sentences = text.replace('\n', ' ').split('. ')
        chunks = []
        current_chunk = []
        current_length = 0
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
                
            if current_length + len(sentence) + 2 <= max_chars:
                current_chunk.append(sentence)
                current_length += len(sentence) + 2
            else:
                if current_chunk:
                    chunks.append('. '.join(current_chunk) + '.')
                current_chunk = [sentence]
                current_length = len(sentence)
                
        if current_chunk:
            chunks.append('. '.join(current_chunk) + '.')
            
        return chunks
    
    def text_to_speech(self, text: str, voice: str, progress_bar) -> List[bytes]:
        """Convert text chunks to speech."""
        if not self.rate_limiter.is_allowed():
            raise Exception("Rate limit exceeded. Please try again later.")
            
        chunks = self.chunk_text(text)
        audio_segments = []
        
        for i, chunk in enumerate(chunks):
            try:
                progress_bar.progress((i + 1) / len(chunks))
                
                audio = generate(
                    text=chunk,
                    voice=voice,
                    model="eleven_monolingual_v1"
                )
                
                audio_segments.append(audio)
                time.sleep(0.5)  # Rate limiting
                
            except Exception as e:
                logger.error(f"Audio generation error: {str(e)}\n{traceback.format_exc()}")
                raise Exception(f"Error generating audio: {str(e)}")
                
        return audio_segments

def initialize_session_state():
    """Initialize session state variables."""
    if 'processed_files' not in st.session_state:
        st.session_state.processed_files = {}
    if 'api_key' not in st.session_state:
        st.session_state.api_key = os.getenv('ELEVENLABS_API_KEY', '')

def main():
    initialize_session_state()
    
    st.title("📚 PDF to Audio Converter")
    st.write("Transform your PDFs into natural-sounding audio using ElevenLabs AI")
    
    # API Key handling
    api_key = st.text_input(
        "Enter your ElevenLabs API key:",
        value=st.session_state.api_key,
        type="password",
        help="Get your API key from https://elevenlabs.io"
    )
    
    if not api_key:
        st.warning("Please enter your ElevenLabs API key to continue.")
        return
        
    try:
        reader = PDFAudioReader(api_key)
        
        # File upload
        uploaded_file = st.file_uploader(
            "Choose a PDF file",
            type="pdf",
            help="Maximum file size: 200MB"
        )
        
        if uploaded_file:
            file_details = {
                "FileName": uploaded_file.name,
                "FileSize": f"{uploaded_file.size / 1024 / 1024:.2f} MB"
            }
            
            st.write("File Details:", file_details)
            
            # Voice selection
            try:
                available_voices = voices()
                voice_names = [voice.name for voice in available_voices]
                selected_voice = st.selectbox(
                    "Select a voice:",
                    voice_names,
                    index=voice_names.index("Josh") if "Josh" in voice_names else 0
                )
            except Exception as e:
                st.error("Error fetching voices. Please check your API key.")
                return
            
            # Convert button
            if st.button("Convert to Audio", type="primary"):
                try:
                    with st.spinner("Processing..."):
                        # Extract text
                        text = reader.extract_text_from_pdf(uploaded_file)
                        st.success("Text extracted successfully!")
                        
                        # Show text preview
                        with st.expander("Preview extracted text"):
                            st.text_area("", text[:1000] + "...", height=200)
                        
                        # Convert to audio
                        progress_bar = st.progress(0)
                        progress_text = st.empty()
                        
                        audio_segments = reader.text_to_speech(
                            text,
                            selected_voice,
                            progress_bar
                        )
                        
                        progress_bar.empty()
                        progress_text.empty()
                        
                        # Display audio players and download buttons
                        st.success(f"Created {len(audio_segments)} audio segments!")
                        
                        for i, audio in enumerate(audio_segments, 1):
                            col1, col2 = st.columns([3, 1])
                            with col1:
                                st.audio(audio, format="audio/mp3")
                            with col2:
                                st.download_button(
                                    f"Download Part {i}",
                                    audio,
                                    file_name=f"{uploaded_file.name}_part_{i}.mp3",
                                    mime="audio/mp3"
                                )
                                
                except Exception as e:
                    st.error(f"Error: {str(e)}")
                    logger.error(f"Processing error: {str(e)}\n{traceback.format_exc()}")
                    
    except Exception as e:
        st.error(f"Error: {str(e)}")
        logger.error(f"Application error: {str(e)}\n{traceback.format_exc()}")

if __name__ == "__main__":
    main()
