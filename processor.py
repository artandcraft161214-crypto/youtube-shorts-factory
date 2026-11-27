import argparse, json, os, subprocess
from pathlib import Path
from urllib.parse import urlparse
from google import genai
from google.genai import types
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import yt_dlp

def main():
    p = argparse.ArgumentParser()
    p.add_argument("url")
    p.add_argument("--upload", action="store_true")
    args = p.parse_args()
    u = urlparse(args.url)
    if u.scheme != "https" or u.hostname not in ("instagram.com", "www.instagram.com"):
        raise ValueError("Use an HTTPS Instagram URL")
    out = Path("output")
    out.mkdir(exist_ok=True)
    with yt_dlp.YoutubeDL({"outtmpl": str(out / "source.%(ext)s"), "format": "bv*+ba/b", "merge_output_format": "mp4", "noplaylist": True}) as ydl:
        info = ydl.extract_info(args.url, download=True)
    source = next(f for f in out.glob("source.*") if f.suffix in (".mp4", ".webm", ".mkv"))
    video = out / "short.mp4"
    subprocess.run(["ffmpeg", "-y", "-i", str(source), "-t", "60", "-vf", "scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", str(video)], check=True)
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    response = client.models.generate_content(model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"), contents=["Analyze this video and generate accurate YouTube Shorts metadata. Return JSON with title ending in #Shorts (max 100 characters), description with relevant hashtags, and tags as an array. Do not invent facts.", types.Part.from_bytes(data=video.read_bytes(), mime_type="video/mp4")], config=types.GenerateContentConfig(response_mime_type="application/json"))
    metadata = json.loads(response.text)
    metadata["title"] = metadata["title"].replace("#Shorts", "").strip()[:92] + " #Shorts"
    metadata["description"] = metadata["description"][:5000]
    tags = []
    for tag in metadata.get("tags", []):
        if isinstance(tag, str) and len(",".join(tags + [tag])) <= 450:
            tags.append(tag)
    metadata["tags"] = tags
    (out / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.upload:
        creds = Credentials(token=None, refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"], token_uri="https://oauth2.googleapis.com/token", client_id=os.environ["YOUTUBE_CLIENT_ID"], client_secret=os.environ["YOUTUBE_CLIENT_SECRET"])
        youtube = build("youtube", "v3", credentials=creds)
        result = youtube.videos().insert(part="snippet,status", body={"snippet": {**metadata, "categoryId": "22"}, "status": {"privacyStatus": "private"}}, media_body=MediaFileUpload(str(video), resumable=True)).execute()
        print("Uploaded privately:", result["id"])

if __name__ == "__main__":
    main()
