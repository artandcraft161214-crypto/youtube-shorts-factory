# YouTube Shorts Factory

Initial Python/GitHub Actions pipeline for authorized Instagram videos, FFmpeg conversion, Gemini metadata and optional private YouTube upload.

## Setup
Add repository Actions secrets: `GEMINI_API_KEY`. For optional upload, also add `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN` (OAuth authorization with YouTube upload scope).

Open Actions > YouTube Shorts Factory > Run workflow. Enter an authorized Instagram Reel URL and leave upload disabled for the first test. Download the shorts-output artifact to review the video and metadata. Enable upload only when ready; uploads are private. Use only content you own or have permission to republish.

## Limitations
Initial implementation is not yet end-to-end tested. Instagram may block downloads from hosted runners. Gemini inline video requests are subject to size and quota limits. The processor currently takes the first 60 seconds, not an AI-selected highlight. Manual metadata editing before upload and automatic public publishing are not implemented. Never commit credentials.
