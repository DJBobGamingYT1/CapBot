import os
import re
import json
import glob
import shutil
import subprocess
import urllib.parse
import urllib.request
import yt_dlp

from youtube_transcript_api import YouTubeTranscriptApi

YT_REGEX = re.compile(r"(https?://(?:www\.)?(?:youtube\.com/watch\?[^\s]+|youtu\.be/[^\s]+))")

TEMP_DIR = "YoutubeToolTemp"
FRAME_COUNT = 6  # how many frames to pull from a video for the local vision model

def find_yt_urls_in_message(text: str):
    """Find YouTube URLs in a piece of text. Returns a list of URLs or None."""
    match = YT_REGEX.findall(text)
    return match if match else None

def get_youtube_video_info(url: str) -> dict:
    """Get the title and channel name of a YouTube video from its URL."""
    oembed_url = "https://www.youtube.com/oembed?url=" + urllib.parse.quote(url, safe="") + "&format=json"
    req = urllib.request.Request(oembed_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=8) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return {
        "title": data.get("title", "Unknown title"),
        "author": data.get("author_name", "Unknown channel"),
        "url": url,
    }

def get_youtube_transcript(video_id: str) -> str:
    """Get the captions/transcript text of a YouTube video from its video id (the part after v= or youtu.be/)."""
    try:
        ytt = YouTubeTranscriptApi()
        fetched = ytt.fetch(video_id)
    except Exception as e:
        return f"No Youtube captions/transcript for this video ({e})"

    lines = [item.text for item in fetched]
    return " ".join(lines)

def download_youtube_video_clip(url: str, out_dir: str = TEMP_DIR) -> str:
    """Download the video to a local file and return its file path."""
    os.makedirs(out_dir, exist_ok=True)
    out_tmpl = os.path.join(out_dir, "clip.%(ext)s")
    opts = {
        "format": "mp4[height<=720]/best[height<=720]/best",
        "outtmpl": out_tmpl,
        "noplaylist": True,
        "quiet": False,
        "overwrites": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info)

def extract_frames(video_path: str, count: int = FRAME_COUNT, out_dir: str = TEMP_DIR) -> list[str]:
    """Pull `count` evenly spaced frames out of a local video file (needs ffmpeg on PATH). Returns image file paths."""
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        print("ffmpeg/ffprobe not found - skipping video frames")
        return []

    for old in glob.glob(os.path.join(out_dir, "frame_*.png")):
        os.remove(old)

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", video_path],
        capture_output=True, text=True,
    )
    try:
        duration = float(probe.stdout.strip())
    except ValueError:
        return []

    frames = []
    for i in range(count):
        t = duration * (i + 0.5) / count
        out_path = os.path.abspath(os.path.join(out_dir, f"frame_{i}.png"))
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.2f}", "-i", video_path,
             "-frames:v", "1", "-vf", "scale=768:-2", out_path],
            stdin=subprocess.DEVNULL,
        )
        if os.path.exists(out_path):
            frames.append(out_path)
    return frames

def yt_videos_to_chat(message) -> list[str]:
    """Download any YouTube videos in the message and return image file paths (frames) for the local vision model."""
    image_paths = []
    ytUrls = find_yt_urls_in_message(message)

    if ytUrls:
        for url in ytUrls:
            try:
                video_path = download_youtube_video_clip(url)
                image_paths.extend(extract_frames(video_path))
            except Exception as e:
                print(f"Could not download {url}: {e}")

    return image_paths