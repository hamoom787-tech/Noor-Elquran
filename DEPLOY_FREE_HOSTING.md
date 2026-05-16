# Free Hosting Deployment

This project is a Flask video-generation app that needs Python, FFmpeg, ImageMagick/Pillow, and optional Whisper.

## Recommended Free Options

### Option A: Render Free Docker Web Service

Render supports Docker web services and free web services can spin down after inactivity. This project includes:

- `Dockerfile`
- `render.yaml`
- `.dockerignore`

Steps:

1. Push this project to a GitHub repository.
2. Create a new Render Blueprint or Web Service from that repository.
3. Choose the included `render.yaml` or Dockerfile.
4. Add environment variables if needed:
   - `GEMINI_API_KEY` for stronger SEO generation.
   - `WHISPER_ENABLED=1` only if the free instance can handle the model load.
5. Deploy.

The default Docker config sets `WHISPER_ENABLED=0` to keep free hosting lighter and avoid model downloads during generation.

### Option B: Hugging Face Spaces Docker

Hugging Face Spaces can run Docker apps on free CPU hardware. It is useful for demo-style ML/video apps, but default disk is ephemeral.

Steps:

1. Create a new Space.
2. Choose Docker as the SDK.
3. Push this project to the Space repository.
4. Keep `PORT=7860`.
5. Add `GEMINI_API_KEY` in Space secrets if you want AI SEO generation.

## Important Limitations

- Free hosting may sleep after inactivity.
- Video generation is CPU-heavy and can be slow.
- Outputs may be temporary on free hosting.
- Whisper can require large downloads and memory, so it is disabled by default in Docker.
- The included `vision/` and `background_audio/` assets are about 162 MB, so the first build can take time.

## Local Docker Test

```powershell
docker build -t quran-reels-generator .
docker run --rm -p 7860:7860 quran-reels-generator
```

Open:

```text
http://127.0.0.1:7860
```
