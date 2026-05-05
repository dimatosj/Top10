# Facebook Saved Videos to Spotify — Design Spec

## Overview

Extend the ig2spotify tool to support Facebook saved videos. Uses Facebook's "Download Your Information" (DYI) data export to get saved post URLs/metadata, then yt-dlp to download videos. The existing extract, analysis, and playlist stages are source-agnostic and require no changes.

## Architecture

**New module:** `fb_downloader.py` — parses Facebook DYI JSON export, extracts video URLs, downloads via yt-dlp with browser cookie authentication.

**Pipeline flow:**
```
Facebook DYI export (JSON) → fb_downloader.py → data/posts/fb_*/ → [existing extract → analysis → playlist]
```

The downstream pipeline (extractor, Claude Code analysis, spotify_client) operates on `data/posts/*/` regardless of source. Facebook posts are distinguished by the `fb_` prefix on their directory names.

## Facebook Export Format

Facebook's DYI export places saved items at:
```
your_facebook_activity/saves_and_collections/saves_and_collections_v2.json
```

Structure:
```json
{
  "saves_and_collections_v2": [
    {
      "timestamp": 1714000000,
      "title": "Post title or caption snippet",
      "data": [
        {
          "text": "Caption or description"
        }
      ],
      "attachments": [
        {
          "data": [
            {
              "external_context": {
                "url": "https://www.facebook.com/watch/?v=123456789"
              }
            }
          ]
        }
      ]
    }
  ]
}
```

**Parsing rules:**
- Iterate `saves_and_collections_v2` array
- Extract URL from `attachments[0].data[0].external_context.url`
- Skip entries without a URL or without a video URL (filter for facebook.com/watch, fb.watch, video patterns)
- Use `timestamp` field (Unix epoch) for metadata
- Use `title` and `data[0].text` for caption

## yt-dlp Integration

**Why yt-dlp:** Facebook videos require authenticated access. yt-dlp handles Facebook's video player, extracts the actual video stream URL, and supports browser cookie extraction for authentication.

**Download command:**
```bash
yt-dlp --cookies-from-browser <browser> -o <output_path> <url>
```

**Configuration:**
- `--browser` option (default: `chrome`) — which browser to extract cookies from
- Supports: `chrome`, `firefox`, `safari`, `edge`, `brave`
- No separate login step needed — reuses the user's existing Facebook browser session

**Error handling:**
- Check yt-dlp is installed (similar to ffmpeg check in extractor)
- Handle: video deleted/private, cookies expired, yt-dlp not found
- Log failures and continue (same pattern as Instagram downloader)

## Post Directory Structure

Facebook posts use `fb_` prefix + video ID as directory name:
```
data/posts/fb_123456789/
  video.mp4
  caption.txt
  metadata.json
```

**metadata.json:**
```json
{
  "shortcode": "fb_123456789",
  "timestamp": "2024-04-25T00:00:00",
  "owner": "facebook",
  "url": "https://www.facebook.com/watch/?v=123456789",
  "source": "facebook"
}
```

The `source` field distinguishes Facebook posts from Instagram posts. The `owner` field is set to `"facebook"` since the DYI export doesn't include the original poster's username.

## CLI Commands

**New commands:**

```
python ig2spotify.py fb-download --export-path <path> [--browser chrome]
python ig2spotify.py fb-run --export-path <path> [--browser chrome]
```

- `fb-download`: Parse export JSON, download videos via yt-dlp
- `fb-run`: Run fb-download + extract in sequence (same pattern as `run`)

**Options:**
- `--export-path` (required): Path to the Facebook DYI export directory (the top-level folder, not the JSON file directly)
- `--browser` (optional, default `chrome`): Browser to extract cookies from

## New Files

| File | Purpose |
|------|---------|
| `fb_downloader.py` | Facebook export parser + yt-dlp download logic |
| `tests/test_fb_downloader.py` | Unit tests for parser and download orchestration |

## Modified Files

| File | Change |
|------|--------|
| `ig2spotify.py` | Add `fb-download` and `fb-run` commands |
| `spotify_client.py` | Source-aware playlist naming (FB vs IG prefix) |
| `requirements.txt` | Add `yt-dlp` |

## Dependencies

- `yt-dlp` — pip install + system binary (like ffmpeg, checked at runtime)

## Idempotency

Same pattern as Instagram downloader:
- Skip posts where `data/posts/fb_<id>/` already exists
- Report processed/skipped/failed counts

## Playlist Naming

Facebook playlists should be named `FB: <date>` (vs. existing `IG: @{owner} - {date}` for Instagram). Since the DYI export doesn't include the original poster's username, we omit the owner for Facebook posts.

**Required change to `spotify_client.py`:** Use the `source` field from metadata to determine the prefix:
- `source == "facebook"` → `"FB: {date}"`
- Otherwise (Instagram, default) → `"IG: @{owner} - {date}"`

## Out of Scope

- Facebook Graph API access (requires app review, not practical for personal use)
- Parsing non-video saved items (photos, links, articles)
- Facebook Reels vs. regular video distinction (yt-dlp handles both)
- Multiple export files or incremental exports
