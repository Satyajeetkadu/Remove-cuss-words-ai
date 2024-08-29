import os
import imageio_ffmpeg as ffmpeg
import subprocess

import streamlit as st
from moviepy.editor import VideoFileClip, AudioFileClip
from pydub import AudioSegment
from pydub.generators import Sine
import whisper_timestamped as whisper
from dotenv import load_dotenv
import re
from thefuzz import fuzz, process  # For fuzzy matching
from openai import OpenAI  # Import OpenAI client


# Use the path provided by imageio-ffmpeg directly
os.environ["IMAGEIO_FFMPEG_EXE"] = ffmpeg.get_ffmpeg_exe()
# Optionally, check if ffmpeg is available

# def check_ffmpeg():
#     try:
#         result = subprocess.run([os.environ["IMAGEIO_FFMPEG_EXE"], '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
#         if result.returncode == 0:
#             print("ffmpeg is installed and available in the path.")
#         else:
#             print("ffmpeg is installed but not available in the path.")
#     except FileNotFoundError:
#         print("ffmpeg is not installed or not available in the path.")

# check_ffmpeg()
# Streamlit app
st.title("Remove Cuss words in one click!")

# Create a directory to save uploaded files
if not os.path.exists("temp"):
    os.makedirs("temp")

# Input OpenAI API Key
openai_api_key = st.text_input("Enter your OpenAI API key", type="password")

# Upload video
uploaded_file = st.file_uploader("Upload an MP4 video", type=["mp4"])

# Input cuss words
cuss_words_input = st.text_input("Enter your cuss words (comma separated)")

def validate_openai_key(api_key):
    try:
        client = OpenAI(api_key=api_key)
        # Attempt a minimal API call to validate the key
        client.chat.completions.create(
            model="gpt-3.5-turbo",  # Using a lightweight model for a quick test
            messages=[
                {"role": "system", "content": "Validate API key."},
                {"role": "user", "content": "Just a test."}
            ]
        )
        print(f"Using OpenAI API Key: {api_key}")  # Print the API key being used
        return True
    except Exception as e:  # Catch all exceptions to handle any type of error
        print(f"OpenAI API key validation failed: {e}")
        return False

# Process video
def process_video(video_path, cuss_words, openai_api_key):
    def transcribe_audio_with_timestamps(audio_file_path):
        # Set the API key environment variable
        os.environ["OPENAI_API_KEY"] = openai_api_key
        
        audio = whisper.load_audio(audio_file_path)
        model = whisper.load_model("base", device="cpu")
        result = whisper.transcribe(model, audio, vad=True, detect_disfluencies=True)
        
        # Extract word timestamps
        word_timestamps = []
        for segment in result['segments']:
            for word in segment['words']:
                word_timestamps.append((word['start'], word['end'], word['text']))
        
        return result['text'], word_timestamps

    def is_cuss_word(word, cuss_words):
        cleaned_word = re.sub(r'[^a-zA-Z]', '', word.lower())
        match, score = process.extractOne(cleaned_word, cuss_words, scorer=fuzz.ratio)
        return score > 85  # Adjust threshold as needed

    def censor_audio(audio_path, word_timestamps):
        audio = AudioSegment.from_file(audio_path, format="mp3")
        detected_cuss_words = []

        for start_time, end_time, word in word_timestamps:
            if is_cuss_word(word, cuss_words):
                detected_cuss_words.append((start_time, end_time, word))
                start_ms = int(start_time * 1000)
                end_ms = int(end_time * 1000)
                beep_duration = end_ms - start_ms
                beep = Sine(1000).to_audio_segment(duration=beep_duration)
                audio = audio[:start_ms] + beep + audio[end_ms:]

        censored_audio_path = audio_path.replace('.mp3', '_censored.mp3')
        audio.export(censored_audio_path, format='mp3')
        return censored_audio_path, detected_cuss_words

    def extract_audio_from_video(video_path):
        video = VideoFileClip(video_path)
        audio_path = video_path.replace('.mp4', '.mp3')
        video.audio.write_audiofile(audio_path, codec='mp3')
        return audio_path

    def replace_audio_in_video(video_path, censored_audio_path):
        video = VideoFileClip(video_path)
        censored_audio = AudioFileClip(censored_audio_path)
        final_video = video.set_audio(censored_audio)
        output_path = video_path.replace('.mp4', '_censored.mp4')
        final_video.write_videofile(output_path, codec='libx264', audio_codec='aac')
        return output_path

    def identify_cuss_words(word_timestamps):
        cuss_word_timestamps = [(start_time, end_time, word) for start_time, end_time, word in word_timestamps if is_cuss_word(word, cuss_words)]
        return cuss_word_timestamps

    # Extract audio from video
    audio_path = extract_audio_from_video(video_path)

    # Transcribe audio and get word-level timestamps
    transcript, word_timestamps = transcribe_audio_with_timestamps(audio_path)
    st.write(f"Transcript: {transcript}")

    # Identify cuss words and print their timestamps
    cuss_word_timestamps = identify_cuss_words(word_timestamps)
    st.write("Cuss words identified at the following timestamps:")
    for start_time, end_time, word in cuss_word_timestamps:
        st.write(f"Cuss word '{word}' from {start_time:.2f}s to {end_time:.2f}s")

    # Censor audio
    censored_audio_path, detected_cuss_words = censor_audio(audio_path, word_timestamps)
    st.write(f"Censored audio saved to: {censored_audio_path}")

    # Replace audio in video
    censored_video_path = replace_audio_in_video(video_path, censored_audio_path)
    st.write(f"Censored video saved to: {censored_video_path}")

    return censored_video_path, cuss_word_timestamps

# Buttons for actions
if st.button("Beep Cuss words"):
    if uploaded_file and cuss_words_input and openai_api_key:
        # Validate OpenAI API key
        if validate_openai_key(openai_api_key):
            # Save uploaded video
            video_path = os.path.join("temp", uploaded_file.name)
            with open(video_path, "wb") as f:
                f.write(uploaded_file.getbuffer())

            # Convert cuss words input to list
            cuss_words = [word.strip() for word in cuss_words_input.split(",")]

            # Process video
            censored_video_path, _ = process_video(video_path, cuss_words, openai_api_key)
            
            # Provide download link for censored video
            st.video(censored_video_path)
            with open(censored_video_path, "rb") as file:
                btn = st.download_button(
                    label="Download Censored Video",
                    data=file,
                    file_name=os.path.basename(censored_video_path),
                    mime="video/mp4"
                )
        else:
            st.write("Invalid OpenAI API key. Please check your key and try again.")
    else:
        st.write("Please upload a video, enter cuss words, and provide your OpenAI API key.")

if st.button("Find Cuss words"):
    if uploaded_file and cuss_words_input and openai_api_key:
        # Validate OpenAI API key
        if validate_openai_key(openai_api_key):
            # Save uploaded video
            video_path = os.path.join("temp", uploaded_file.name)
            with open(video_path, "wb") as f:
                f.write(uploaded_file.getbuffer())

            # Convert cuss words input to list
            cuss_words = [word.strip() for word in cuss_words_input.split(",")]

            # Process video to find cuss words
            _, cuss_word_timestamps = process_video(video_path, cuss_words, openai_api_key)
            
            # Display cuss words and their timestamps
            st.write("Cuss words identified at the following timestamps:")
            for start_time, end_time, word in cuss_word_timestamps:
                st.write(f"Cuss word '{word}' from {start_time:.2f}s to {end_time:.2f}s")
        else:
            st.write("Invalid OpenAI API key. Please check your key and try again.")
    else:
        st.write("Please upload a video, enter cuss words, and provide your OpenAI API key.")
