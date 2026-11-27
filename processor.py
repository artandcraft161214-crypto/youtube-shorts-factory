import argparse, json, os, subprocess, time
from pathlib import Path
from urllib.parse import urlparse
from google import genai
from google.genai import types
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import yt_dlp
from yt_dlp.utils import DownloadError

def run(*args):
    subprocess.run(args, check=True)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("url")
    p.add_argument("--upload", action="store_true")
    p.add_argument("--privacy", choices=["private", "unlisted", "public"], default="private")
    args = p.parse_args()
    out = Path("output")
    out.mkdir(exist_ok=True)
    u = urlparse(args.url)
    if u.scheme != "https" or u.hostname not in ("youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"):
        raise ValueError("Use an HTTPS YouTube video URL")
    options = {"outtmpl": str(out / "source.%(ext)s"), "format": "bv*[height<=1080]+ba/b[height<=1080]", "merge_output_format": "mp4", "noplaylist": True, "js_runtimes": {"deno": {}}}
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(args.url, download=True)
    except DownloadError as exc:
        if "Sign in to confirm" in str(exc) or "not a bot" in str(exc):
            raise RuntimeError("YouTube requested bot verification and blocked this GitHub-hosted download. No reliable code-only workaround is available for this runner; the clip-processing stage was not reached.") from exc
        raise
    source = next(f for f in out.glob("source.*") if f.suffix in (".mp4", ".webm", ".mkv"))
    duration = float(info["duration"])
    if duration < 300:
        raise ValueError("At least 5 minutes needed for ten non-overlapping 30-second clips")
    proxy = out / "analysis.mp4"
    run("ffmpeg", "-y", "-i", str(source), "-vf", "scale=-2:360", "-r", "2", "-c:v", "libx264", "-crf", "30", "-c:a", "aac", "-b:a", "64k", str(proxy))
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    remote = client.files.upload(file=str(proxy))
    try:
        for _ in range(120):
            if remote.state.name != "PROCESSING":
                break
            time.sleep(5)
            remote = client.files.get(name=remote.name)
        if remote.state.name != "ACTIVE":
            raise RuntimeError("Gemini video processing failed or timed out")
        prompt = f"""Analyze the entire video (duration {duration} seconds). Select exactly 10 distinct non-overlapping engaging excerpts, each 30 to 60 seconds, with complete thoughts and strong opening hooks. Use absolute timestamps in seconds. Rank by predicted engagement, not chronological order. Return a JSON object with clips array; each clip has start, end, title, description, hashtags (array), tags (array), hook, reason. Metadata must match actual excerpt and language; avoid invented claims. Titles end in #Shorts. Choose natural boundaries."""
        response = client.models.generate_content(model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"), contents=[remote, prompt], config=types.GenerateContentConfig(response_mime_type="application/json"))
        clips = json.loads(response.text)["clips"]
    finally:
        client.files.delete(name=remote.name)
    if len(clips) != 10:
        raise ValueError("Gemini did not return exactly ten clips")
    intervals = []
    for c in clips:
        s, e = float(c["start"]), float(c["end"])
        if not (0 <= s < e <= duration and 30 <= e-s <= 60) or any(s < b and e > a for a,b in intervals):
            raise ValueError("Invalid or overlapping Gemini clip timestamps")
        intervals.append((s,e))
    manifest = []
    for i,c in enumerate(clips,1):
        folder = out / f"short_{i:02d}"
        folder.mkdir(exist_ok=True)
        video = folder / "short.mp4"
        hook = folder / "hook.txt"
        hook.write_text(str(c["hook"]).replace("\n"," ")[:65], encoding="utf-8")
        vf = f"scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:textfile={hook}:expansion=none:fontsize=38:fontcolor=white:box=1:boxcolor=black@0.7:x=(w-tw)/2:y=220:enable='lt(t,3)'"
        run("ffmpeg","-y","-ss",str(c["start"]),"-i",str(source),"-t",str(float(c["end"])-float(c["start"])),"-vf",vf,"-af","loudnorm","-c:v","libx264","-preset","fast","-pix_fmt","yuv420p","-c:a","aac","-movflags","+faststart",str(video))
        tags = []
        for tag in c["tags"]:
            if isinstance(tag,str) and len(",".join(tags+[tag])) <= 450:
                tags.append(tag)
        hashtags = " ".join("#"+str(h).lstrip("#").replace(" ","") for h in c["hashtags"][:15])
        metadata = {"title":str(c["title"]).replace("#Shorts","").strip()[:92]+" #Shorts","description":(str(c["description"])+"\n\n"+hashtags)[:5000],"tags":tags}
        (folder/"metadata.json").write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding="utf-8")
        manifest.append({"clip":i,"start":c["start"],"end":c["end"],"reason":c["reason"],"metadata":metadata})
    manifest_path = out/"manifest.json"
    def save():
        manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    save()
    if args.upload:
        creds = Credentials(token=None, refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"], token_uri="https://oauth2.googleapis.com/token", client_id=os.environ["YOUTUBE_CLIENT_ID"], client_secret=os.environ["YOUTUBE_CLIENT_SECRET"])
        youtube = build("youtube","v3",credentials=creds)
        for item in manifest:
            video = out / f"short_{item['clip']:02d}" / "short.mp4"
            result = youtube.videos().insert(part="snippet,status",body={"snippet":{**item["metadata"],"categoryId":"22"},"status":{"privacyStatus":args.privacy}},media_body=MediaFileUpload(str(video),resumable=True)).execute()
            item["youtube_id"] = result["id"]
            save()
            print("Uploaded:",result["id"])

if __name__ == "__main__":
    main()
