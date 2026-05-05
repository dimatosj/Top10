# ig2spotify — Instagram Saved Videos to Spotify Playlists

## Overview

A CLI tool that downloads saved Instagram videos, transcribes and analyzes them for explicit music album recommendations using the Claude API, and creates per-video Spotify playlists containing the full albums mentioned.

## Architecture

Modular CLI with three independent stages that communicate through a shared `data/` directory. Each stage is idempotent — it checks for existing output before processing, so re-runs skip completed work.

### Subcommands

| Command | Purpose |
|---------|---------|
| `download` | Pull saved videos from Instagram |
| `extract` | Extract audio from downloaded videos via ffmpeg |
| `playlist` | Search Spotify for albums, create playlists |
| `run` | Execute download + extract in sequence (analysis done by Claude Code, then run `playlist`) |

### Project Structure

```
instagram/
├── ig2spotify.py          # CLI entry point (click)
├── config.py              # Loads .env, validates required keys
├── downloader.py          # instaloader logic
├── extractor.py           # ffmpeg audio extraction
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

**Performed by:** Claude Code (not a Python script)

This stage runs inside a Claude Code session. The user asks Claude Code to analyze the downloaded posts, and Claude Code:

1. Runs `python ig2spotify.py extract` to extract audio from all downloaded videos via ffmpeg
2. Iterates through each post in `data/posts/<shortcode>/`
3. Reads the audio file and caption for each post
4. Identifies explicitly named albums — only where title and artist are clearly stated or unambiguously identifiable
5. Writes analysis results to `data/analysis/<shortcode>.json`

**Audio extraction helper** (`analyze` subcommand in the CLI):
- `python ig2spotify.py extract` — uses ffmpeg to extract MP3 audio from each video in `data/posts/`
- Saves audio as `data/posts/<shortcode>/audio.mp3`
- Skips posts that already have an extracted audio file
- Fails fast if ffmpeg is not installed

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

**Idempotency:** Skip posts that already have an analysis file.

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
SPOTIFY_CLIENT_ID=...
SPOTIFY_CLIENT_SECRET=...
SPOTIFY_REDIRECT_URI=http://localhost:8888/callback
```

**`config.py`:** Loads `.env` via `python-dotenv`, validates all required keys are present, fails fast with clear error messages.

## CLI Interface

Built with `click`. Shared `--data-dir` option (defaults to `./data`).

```
python ig2spotify.py download --username <ig_username>
python ig2spotify.py extract
python ig2spotify.py playlist
python ig2spotify.py run --username <ig_username>
```

Note: The `run` command executes `download` → `extract` → `playlist`. The analysis step (between `extract` and `playlist`) is performed by Claude Code in-session — it reads the audio files and captions, identifies albums, and writes analysis JSONs.

## Dependencies

**Python packages:**
- `instaloader` — Instagram download
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
