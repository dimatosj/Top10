# Top10

Turn music recommendation videos from Instagram and Facebook into playlists on Spotify and Qobuz.

The pipeline downloads saved videos, extracts audio, transcribes with Whisper, then creates playlists from the albums mentioned. A fuzzy verification step catches Whisper transcription errors (e.g. "Lost Cat" -> LAUSSE THE CAT) before anything hits the streaming services.

## Pipeline

```
download -> extract -> [transcribe with Whisper] -> verify -> derive-genres -> playlist
```

1. **Download** saved videos from Instagram or a Facebook DYI export
2. **Extract** audio from each video with ffmpeg
3. **Transcribe** audio with Whisper and identify albums (manual step with Claude or any LLM)
4. **Verify** album names against Spotify's catalog, auto-correcting Whisper errors
5. **Derive genres** from Qobuz metadata for playlist naming
6. **Create playlists** on Spotify and/or Qobuz, named `@poster [Genre]`

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium  # only needed for Qobuz token extraction
cp .env.example .env
# fill in .env with your credentials
```

### Spotify

Create a [Spotify Developer](https://developer.spotify.com/dashboard) app and add the client ID, secret, and redirect URI to `.env`. Add your Spotify account email under "Users and Access" in the dashboard.

### Qobuz (optional)

The Qobuz `user/login` API endpoint is broken upstream as of April 2026. Use token auth instead:

1. Log in at [play.qobuz.com](https://play.qobuz.com)
2. DevTools (Cmd+Option+I) -> Application -> Local Storage -> `https://play.qobuz.com`
3. Find the `localuser` key, copy `token` and `id` into `.env` as `QOBUZ_TOKEN` and `QOBUZ_USER_ID`

## Usage

### Instagram

```bash
# Download + extract audio
python ig2spotify.py run --username <instagram_user>

# Transcribe audio files in data/audio/ with Whisper, then have an LLM
# identify albums and write JSON to data/analysis/. Each file should contain:
# {"albums": [{"artist": "...", "album": "..."}], "has_music": true}

# Verify and correct Whisper errors against Spotify
python ig2spotify.py verify

# Tag with genres and create playlists
python ig2spotify.py derive-genres
python ig2spotify.py playlist
python ig2spotify.py qobuz-playlist
```

### Facebook

```bash
# Point at your Facebook DYI export directory
python ig2spotify.py fb-run --export-path /path/to/facebook/export

# Then same flow: transcribe, verify, derive-genres, playlist
```

## Commands

| Command | Description |
|---|---|
| `download` | Download saved videos from Instagram |
| `extract` | Extract audio from videos with ffmpeg |
| `fb-download` | Download saved videos from Facebook export |
| `fb-run` | Run fb-download + extract in sequence |
| `run` | Run download + extract in sequence |
| `verify` | Verify album names against Spotify, auto-correct Whisper errors |
| `derive-genres` | Tag analysis files with genre from Qobuz |
| `playlist` | Create Spotify playlists |
| `qobuz-playlist` | Create Qobuz playlists |
| `qobuz-verify` | Check album availability on Qobuz |

## How verification works

Whisper frequently garbles artist and album names. The `verify` command searches Spotify with three progressively looser strategies:

1. **Artist search** -- find albums by the transcribed artist, require both artist and album names to be close
2. **Album title search** -- search by album name alone, catches completely wrong artist names
3. **Combined free-text search** -- artist + album as free text, catches cases where both have minor errors

Name comparison uses Levenshtein distance (up to 15% of string length), punctuation normalization, and length-aware substring matching to avoid false positives.

## Data layout

```
data/
  posts/<shortcode>/       # downloaded videos + metadata
  audio/<shortcode>.mp3    # extracted audio
  analysis/<shortcode>.json # transcription + identified albums + genre
  playlists/<shortcode>.json # created playlist IDs and results
```
