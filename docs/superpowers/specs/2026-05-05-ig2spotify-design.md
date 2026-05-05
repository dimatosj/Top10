# ig2spotify — Instagram Saved Videos to Spotify Playlists

## Overview

A CLI tool that downloads saved Instagram videos, transcribes and analyzes them for explicit music album recommendations using the Claude API, and creates per-video Spotify playlists containing the full albums mentioned.

## Architecture

Modular CLI with three independent stages that communicate through a shared `data/` directory. Each stage is idempotent — it checks for existing output before processing, so re-runs skip completed work.

### Subcommands

| Command | Purpose |
|---------|---------|
| `download` | Pull saved videos from Instagram |
| `analyze` | Extract audio, transcribe via Claude, identify albums |
| `playlist` | Search Spotify for albums, create playlists |
| `run` | Execute all three stages in sequence |

### Project Structure

```
instagram/
├── ig2spotify.py          # CLI entry point (click)
├── config.py              # Loads .env, validates required keys
├── downloader.py          # instaloader logic
├── analyzer.py            # audio extraction + Claude API
├── spotify_client.py      # Spotify search + playlist creation
├── requirements.txt
├── .env                   # secrets (not committed)
└── data/                  # created at runtime
    ├── posts/
    │   └── <shortcode>/
    │       ├── video.mp4
    │       ├── caption.txt
    │       └── metadata.json
    ├── analysis/
    │   └── <shortcode>.json
    └── playlists/
        └── <shortcode>.json
```

## Stage 1: Download

**Module:** `downloader.py`

**Authentication:**
- Interactive login via instaloader (username + password + 2FA code)
- Session persisted to `~/.config/instaloader/session-<username>` (instaloader default)
- Subsequent runs reuse the saved session
- On expired session: detect error, prompt user to re-authenticate

**Behavior:**
- Iterate all posts in the default saved collection (`instaloader :saved`)
- For each post:
  - Skip non-video posts (photos, carousels without video)
  - Skip posts already present in `data/posts/<shortcode>/`
  - Save: video file (`.mp4`), caption text (`caption.txt`), metadata (`metadata.json`)
- Metadata includes: shortcode, timestamp, owner username, post URL
- Carousel posts: extract only video components

**Rate limiting:** Relies on instaloader's built-in rate limit handling with backoff.

**CLI:**
```
python ig2spotify.py download --username <ig_username> [--data-dir ./data]
```

## Stage 2: Analyze

**Module:** `analyzer.py`

**Audio extraction:**
- Use `ffmpeg` via subprocess to extract MP3 audio from each video
- Audio file is temporary — deleted after Claude API call
- Fail fast at startup if `ffmpeg` is not installed

**Claude API call:**
- Send audio (base64-encoded) + caption text in a single message
- Claude transcribes the audio and identifies explicitly named albums in one call
- Strict extraction: only albums where title and artist are clearly stated or unambiguously identifiable

**Prompt:**
```
You are analyzing an Instagram video about music.
I'm providing the audio and the post caption.

Transcribe what is said, then identify any music albums
that are explicitly recommended by name. Only include albums
where both the album title and artist are clearly stated
or unambiguously identifiable.

Return JSON:
{
  "transcript": "...",
  "albums": [
    {"artist": "...", "album": "..."}
  ]
}

If no albums are explicitly mentioned, return an empty albums array.
```

**Output:** `data/analysis/<shortcode>.json`
```json
{
  "transcript": "full transcription text",
  "albums": [
    {"artist": "Radiohead", "album": "Kid A"}
  ],
  "has_music": true
}
```

**Cost control:** Before processing, print the number of videos to analyze and estimated audio minutes. Prompt for user confirmation before proceeding.

**Idempotency:** Skip posts that already have an analysis file.

**CLI:**
```
python ig2spotify.py analyze [--data-dir ./data]
```

## Stage 3: Playlist

**Module:** `spotify_client.py`

**Authentication:**
- `spotipy` library with OAuth2 authorization code flow
- Scopes: `playlist-modify-public`, `playlist-modify-private`
- First run: opens browser for Spotify OAuth, caches refresh token (`.cache`)
- Subsequent runs reuse cached token

**Album search:**
- For each album in the analysis result: `sp.search(q="album:{album} artist:{artist}", type="album")`
- Take the first result; log warning and skip if no match found
- Collect all track URIs via `sp.album_tracks()`

**Playlist creation:**
- One playlist per video/post
- Name: `"IG: @{poster_username} - {date}"`
- Description: original Instagram caption (truncated to 300 chars)
- Add all tracks from all matched albums
- Batch track additions (spotipy max 100 per call)

**Output:** `data/playlists/<shortcode>.json`
```json
{
  "playlist_id": "...",
  "playlist_url": "...",
  "albums_added": [
    {"artist": "Radiohead", "album": "Kid A", "spotify_album_id": "..."}
  ],
  "albums_not_found": []
}
```

**Edge cases:**
- Album not found on Spotify: log warning, continue
- No albums in analysis: skip playlist creation (no empty playlists)
- Duplicate albums across videos: fine — each video is its own playlist

**Idempotency:** Skip posts that already have a playlist file.

**CLI:**
```
python ig2spotify.py playlist [--data-dir ./data]
```

## Configuration

**`.env` file:**
```
ANTHROPIC_API_KEY=sk-...
SPOTIFY_CLIENT_ID=...
SPOTIFY_CLIENT_SECRET=...
SPOTIFY_REDIRECT_URI=http://localhost:8888/callback
```

**`config.py`:** Loads `.env` via `python-dotenv`, validates all required keys are present, fails fast with clear error messages.

## CLI Interface

Built with `click`. Shared `--data-dir` option (defaults to `./data`).

```
python ig2spotify.py download --username <ig_username>
python ig2spotify.py analyze
python ig2spotify.py playlist
python ig2spotify.py run --username <ig_username>
```

## Dependencies

**Python packages:**
- `instaloader` — Instagram download
- `anthropic` — Claude API
- `spotipy` — Spotify API
- `click` — CLI framework
- `python-dotenv` — environment loading

**System:**
- `ffmpeg` — audio extraction (checked at startup of `analyze` stage)

## Error Handling

- Each stage prints progress (e.g., "Analyzing post 3/47...")
- Failed individual posts do not halt the pipeline — errors are logged, post is skipped
- Summary printed at end of each stage: processed count, skipped count, failed count with reasons

## What This Tool Does NOT Do

- OCR or visual analysis of video frames
- Fuzzy matching or guessing at album names
- Deduplication of albums across playlists
- Downloading non-video saved posts
