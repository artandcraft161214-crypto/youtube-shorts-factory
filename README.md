# YouTube Shorts Factory

Convert an authorized long YouTube video into ten non-overlapping 30–60 second Shorts using Gemini video analysis, FFmpeg vertical padding, hook overlay, audio normalization, individual SEO metadata and optional automatic YouTube upload.

Configure GEMINI_API_KEY and, for uploads, YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN. Run Actions > YouTube Shorts Factory with youtube_url. Test with upload disabled first. Upload visibility defaults to private; public is selectable. Use only videos you have permission to download and republish.

Minimum source duration: 5 minutes. Gemini timestamp validation rejects invalid selections. Output artifact contains clips and manifest. Not yet end-to-end tested. YouTube download restrictions, Gemini file/context limits, upload quota and API project restrictions may prevent completion. Captions and subject tracking are not yet implemented. Rerunning an upload can duplicate videos.

## YouTube download failures
The hosted GitHub runner installs Deno and yt-dlp EJS support to handle YouTube's JavaScript extraction requirements. This cannot guarantee downloads: YouTube may still require bot verification or block GitHub's cloud IP. If so, consider a self-hosted runner on an authorized machine or process a video file you own locally. Do not publish or share YouTube account cookies in repository secrets/logs.
