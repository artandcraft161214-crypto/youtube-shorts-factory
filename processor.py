import argparse, json, os, subprocess, time, re
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse
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
    class DownloadDiagnostics:
        blocked = False
        rate_limited = False
        def debug(self, msg):
            print(msg)
        def warning(self, msg):
            if "429" in msg or "Too Many Requests" in msg:
                self.rate_limited = True
            print("WARNING: " + msg)
        def error(self, msg):
            if "Sign in to confirm" in msg or "not a bot" in msg:
                self.blocked = True
            print("ERROR: " + msg)

    diag = DownloadDiagnostics()
    options = {"logger": diag, "retries": 0, "extractor_retries": 0, "fragment_retries": 0, "outtmpl": str(out / "source.%(ext)s"), "format": "bv*[height<=1080]+ba/b[height<=1080]", "merge_output_format": "mp4", "noplaylist": True, "js_runtimes": {"deno": {}}}
    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(args.url, download=True)
    except DownloadError as exc:
        if diag.blocked or diag.rate_limited or "Sign in to confirm" in str(exc) or "not a bot" in str(exc) or "429" in str(exc):
            raise RuntimeError("YOUTUBE_ACCESS_BLOCKED: GitHub-hosted runner received YouTube rate-limiting (HTTP 429) and/or bot verification. Stopping without retries; Local analysis and Shorts generation were not reached. This is a YouTube access restriction, not a code or Gemini-key failure.") from exc
        raise
    source = next(f for f in out.glob("source.*") if f.suffix in (".mp4", ".webm", ".mkv"))
    duration = float(info["duration"])
    if duration < 300:
        raise ValueError("At least 5 minutes needed for ten non-overlapping 30-second clips")
    from faster_whisper import WhisperModel
    from scenedetect import detect, ContentDetector
    print("Analyzing scenes and speech locally", flush=True)
    scenes = detect(str(source), ContentDetector(threshold=27), start_in_scene=True)
    cuts = [x[0].get_seconds() for x in scenes]
    model = WhisperModel("small", device="cpu", compute_type="int8", cpu_threads=2)
    segments, language = model.transcribe(str(source), vad_filter=True)
    speech = list(segments)
    # Partition the timeline into ten disjoint regions, then score candidate windows.
    clips = []
    for i in range(10):
        lo, hi = duration*i/10, min(duration, duration*(i+1)/10)
        length = min(45.0, hi-lo)
        candidates = sorted(set([lo, max(lo, hi-length)] + [x for x in cuts if lo <= x <= hi-length] + [x.start for x in speech if lo <= x.start <= hi-length]))
        def score(start):
            end = start+length
            words = sum(len(x.text.split()) for x in speech if x.start >= start and x.end <= end)
            changes = sum(start < x < end for x in cuts)
            return min(words, 130)/20 + min(changes, 8)*0.4
        start = max(candidates, key=score)
        end = min(hi, start+length)
        excerpt = " ".join(x.text.strip() for x in speech if x.start >= start and x.end <= end)
        words = Counter(re.findall(r"[^\W\d_]{4,}", excerpt.lower()))
        tags = [w for w,n in words.most_common(12)]
        title = " ".join(excerpt.split()[:9]) or str(info.get("title","Video highlight"))
        clips.append(dict(start=start,end=end,title=title,description=excerpt[:4000] or str(info.get("title","Video highlight")),hashtags=["Shorts"]+tags[:5],tags=tags,hook=title,reason="Local speech density and scene-change score",score=score(start)))
    clips.sort(key=lambda c:c["score"], reverse=True)
    if len(clips) != 10:
        raise ValueError("Local analysis did not return exactly ten clips")
    intervals = []
    for c in clips:
        s, e = float(c["start"]), float(c["end"])
        if not (0 <= s < e <= duration and 29.999999 <= e-s <= 60) or any(s < b and e > a for a,b in intervals):
            raise ValueError("Invalid or overlapping local clip timestamps")
        intervals.append((s,e))
    manifest = []
    for i,c in enumerate(clips,1):
        folder = out / f"short_{i:02d}"
        folder.mkdir(exist_ok=True)
        video = folder / "short.mp4"
        hook = folder / "hook.txt"
        hook.write_text(str(c["hook"]).replace("\n"," ")[:65], encoding="utf-8")
        def stamp(t):
            ms = max(0, round(t*1000))
            return f"{ms//3600000:02d}:{ms//60000%60:02d}:{ms//1000%60:02d},{ms%1000:03d}"
        cues = []
        for seg in speech:
            left, right = max(float(c["start"]), seg.start), min(float(c["end"]), seg.end)
            if right > left and seg.text.strip():
                cues.append(f"{len(cues)+1}\n{stamp(left-float(c['start']))} --> {stamp(right-float(c['start']))}\n{seg.text.strip()}\n")
        subtitle = folder / "captions.srt"
        subtitle.write_text("\n".join(cues), encoding="utf-8")
        vf = f"scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,drawtext=fontfile=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf:textfile={hook}:expansion=none:fontsize=38:fontcolor=white:box=1:boxcolor=black@0.7:x=(w-tw)/2:y=220:enable='lt(t,3)'"
        if cues:
            vf += f",subtitles={subtitle}:force_style='FontSize=18,Alignment=2,MarginV=45'"
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
