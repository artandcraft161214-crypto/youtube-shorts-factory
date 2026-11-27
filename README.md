# YouTube Shorts Factory

GitHub-hosted workflow that accepts **only a YouTube long-video URL** and aims to generate ten non-overlapping 30–60 second Shorts, using Gemini video analysis, FFmpeg vertical editing and hook overlay, individual title/SEO metadata, and optional automatic YouTube upload.

## Setup
Add GitHub Actions secret `GEMINI_API_KEY`. For uploading also add `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, and `YOUTUBE_REFRESH_TOKEN` (with YouTube upload OAuth scope). Run **Actions > YouTube Shorts Factory > Run workflow** and enter your authorized YouTube video URL. Leave upload disabled until processing succeeds. Video uploads, if enabled, default to private.

## Critical limitation: YouTube downloader
GitHub-hosted runners are currently receiving **"Sign in to confirm you're not a bot"** for the tested YouTube URL, even with Deno/EJS installed. This is YouTube access control, not a Gemini failure. No guaranteed code-only fix has been established; repeating the same link on GitHub Actions is likely to fail at download again. The pipeline has **not** successfully generated ten Shorts end to end. There is deliberately no direct MP4 URL or self-hosted runner option in this project.

## Additional notes
The video must be at least five minutes long to select ten non-overlapping clips of at least 30 seconds. Processing can also be constrained by Gemini file limits, rate limits, YouTube upload quota, or other API restrictions. Captions and smart subject-tracking are not implemented. Only process content you own or have permission to republish. Never commit credentials.
