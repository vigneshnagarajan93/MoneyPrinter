import os
import uuid
import requests
import srt_equalizer
import assemblyai as aai

from typing import List
from moviepy.editor import *
from termcolor import colored
from dotenv import load_dotenv
from datetime import timedelta
from moviepy.video.fx.all import crop
from moviepy.video.tools.subtitles import SubtitlesClip

load_dotenv("../.env")
ASSEMBLY_AI_API_KEY = os.getenv("ASSEMBLY_AI_API_KEY")

def save_video(video_url: str, directory: str = "../temp") -> str:
    video_id = uuid.uuid4()
    video_path = f"{directory}/{video_id}.mp4"
    with open(video_path, "wb") as f:
        f.write(requests.get(video_url).content)
    return video_path

def __generate_subtitles_assemblyai(audio_path: str, voice: str) -> str:
    language_mapping = {"br": "pt", "id": "en", "jp": "ja", "kr": "ko"}
    lang_code = language_mapping.get(voice, voice)
    aai.settings.api_key = ASSEMBLY_AI_API_KEY
    config = aai.TranscriptionConfig(language_code=lang_code)
    transcriber = aai.Transcriber(config=config)
    transcript = transcriber.transcribe(audio_path)
    return transcript.export_subtitles_srt()

def __generate_subtitles_locally(sentences: List[str], audio_clips: List[AudioFileClip]) -> str:
    def convert_to_srt_time_format(total_seconds):
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = int(total_seconds % 60)
        milliseconds = int((total_seconds - int(total_seconds)) * 1000)
        return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"

    
    start_time = 0
    subtitles = []

    for i, (sentence, audio_clip) in enumerate(zip(sentences, audio_clips), start=1):
        duration = audio_clip.duration
        end_time = start_time + duration
        subtitle_entry = f"{i}\n{convert_to_srt_time_format(start_time)} --> {convert_to_srt_time_format(end_time)}\n{sentence}\n"
        subtitles.append(subtitle_entry)
        start_time += duration

    return "\n".join(subtitles)

def generate_subtitles(audio_path: str, sentences: List[str], audio_clips: List[AudioFileClip], voice: str) -> str:
    def equalize_subtitles(srt_path: str, max_chars: int = 10) -> None:
        srt_equalizer.equalize_srt_file(srt_path, srt_path, max_chars)

    subtitles_path = f"../subtitles/{uuid.uuid4()}.srt"
    if ASSEMBLY_AI_API_KEY:
        print(colored("[+] Creating subtitles using AssemblyAI", "blue"))
        subtitles = __generate_subtitles_assemblyai(audio_path, voice)
    else:
        print(colored("[+] Creating subtitles locally", "blue"))
        subtitles = __generate_subtitles_locally(sentences, audio_clips)

    with open(subtitles_path, "w") as file:
        file.write(subtitles)

    equalize_subtitles(subtitles_path)
    print(colored("[+] Subtitles generated.", "green"))
    return subtitles_path

def combine_videos(video_paths: List[str], max_duration: int, max_clip_duration: int, threads: int) -> str:
    video_id = uuid.uuid4()
    combined_video_path = f"../temp/{video_id}.mp4"
    req_dur = max_duration / len(video_paths)
    print(colored("[+] Combining videos...", "blue"))
    print(colored(f"[+] Each clip will be maximum {req_dur} seconds long.", "blue"))

    clips = []
    tot_dur = 0
    while tot_dur < max_duration:
        for video_path in video_paths:
            clip = VideoFileClip(video_path).without_audio()
            if (max_duration - tot_dur) < clip.duration:
                clip = clip.subclip(0, (max_duration - tot_dur))
            elif req_dur < clip.duration:
                clip = clip.subclip(0, req_dur)
            clip = clip.set_fps(30)
            aspect_ratio = round((clip.w / clip.h), 4)
            if aspect_ratio < 0.5625:
                clip = crop(clip, width=clip.w, height=round(clip.w / 0.5625),
                            x_center=clip.w / 2, y_center=clip.h / 2)
            else:
                clip = crop(clip, width=round(0.5625 * clip.h), height=clip.h,
                            x_center=clip.w / 2, y_center=clip.h / 2)
            clip = clip.resize((1080, 1920))
            if clip.duration > max_clip_duration:
                clip = clip.subclip(0, max_clip_duration)
            clips.append(clip)
            tot_dur += clip.duration

    final_clip = concatenate_videoclips(clips).set_fps(30)
    final_clip.write_videofile(combined_video_path, threads=threads)
    return combined_video_path

def generate_video(combined_video_path: str, tts_path: str, subtitles_path: str, threads: int, subtitles_position: str, text_color: str) -> str:
    print(f"[DEBUG] Subtitles position: {subtitles_position}")
    try:
        horizontal_subtitles_position, vertical_subtitles_position = subtitles_position.split(",")
    except Exception:
        print(colored("[!] Invalid subtitles_position format. Defaulting to center,bottom", "yellow"))
        horizontal_subtitles_position, vertical_subtitles_position = "center", "bottom"

    generator = lambda txt: TextClip(
        txt,
        font="../fonts/bold_font.ttf",
        fontsize=100,
        color=text_color,
        stroke_color="black",
        stroke_width=5,
    )

    subtitles = SubtitlesClip(subtitles_path, generator)
    result = CompositeVideoClip([
        VideoFileClip(combined_video_path),
        subtitles.set_pos((horizontal_subtitles_position, vertical_subtitles_position))
    ])

    audio = AudioFileClip(tts_path)
    result = result.set_audio(audio)
    result.write_videofile("../temp/output.mp4", threads=threads or 2)
    return "output.mp4"
