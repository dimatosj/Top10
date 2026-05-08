import json
import os
import requests
import spotipy
from spotipy.oauth2 import SpotifyOAuth


def get_spotify_client(config):
    return spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=config.spotify_client_id,
        client_secret=config.spotify_client_secret,
        redirect_uri=config.spotify_redirect_uri,
        scope="playlist-modify-public playlist-modify-private",
    ))


def build_search_query(artist, album):
    return f"album:{album} artist:{artist}"


def add_tracks_batched(sp, playlist_id, track_uris):
    for i in range(0, len(track_uris), 100):
        sp.playlist_add_items(playlist_id, track_uris[i:i + 100])


def search_album(sp, artist, album):
    query = build_search_query(artist, album)
    results = sp.search(q=query, type="album", limit=1)
    items = results["albums"]["items"]
    if not items:
        return None
    return items[0]


def get_album_track_uris(sp, album_id):
    uris = []
    results = sp.album_tracks(album_id)
    uris.extend(t["uri"] for t in results["items"])
    while results["next"]:
        results = sp.next(results)
        uris.extend(t["uri"] for t in results["items"])
    return uris


def _levenshtein(a, b):
    if len(a) < len(b):
        a, b = b, a
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (ca != cb)))
        prev = curr
    return prev[-1]


def _names_close(a, b):
    """Check if two names are close enough to be transcription variants."""
    a, b = a.lower().strip(), b.lower().strip()
    if a == b:
        return True
    strip = lambda s: s.replace(" ", "").replace("-", "").replace("&", "and").replace(".", "").replace(",", "").replace(";", "").replace(":", "")
    sa, sb = strip(a), strip(b)
    if sa == sb:
        return True
    # One is a substring of the other, but only if lengths are similar
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if len(shorter) > 3 and shorter in longer and len(shorter) >= len(longer) * 0.5:
        return True
    # Allow small edit distance relative to string length
    dist = _levenshtein(sa, sb)
    max_len = max(len(sa), len(sb))
    if max_len > 0 and dist <= max(2, max_len * 0.15):
        return True
    return False


def _fuzzy_find_album(sp, artist, album):
    """Search Spotify with progressively looser queries to find a misnamed album."""
    # Pass 1: search by artist, require both artist+album close
    for query in [f"artist:{artist}", artist]:
        results = sp.search(q=query, type="album", limit=10)
        for item in results["albums"]["items"]:
            sp_artist = item["artists"][0]["name"]
            sp_album = item["name"]
            if _names_close(sp_artist, artist) and _names_close(sp_album, album):
                return item, sp_artist, sp_album

    # Pass 2: search by album title alone — catches cases where Whisper
    # completely garbled the artist name but got the album right
    for query in [f"album:{album}", album]:
        results = sp.search(q=query, type="album", limit=10)
        for item in results["albums"]["items"]:
            sp_album = item["name"]
            if _names_close(sp_album, album):
                sp_artist = item["artists"][0]["name"]
                return item, sp_artist, sp_album

    # Pass 3: search by artist+album as free text — catches partial matches
    # where both fields have minor errors. Require album match (more
    # distinctive than artist) and album title long enough to avoid false hits.
    if len(album) >= 8:
        results = sp.search(q=f"{artist} {album}", type="album", limit=10)
        for item in results["albums"]["items"]:
            sp_artist = item["artists"][0]["name"]
            sp_album = item["name"]
            if _names_close(sp_album, album):
                return item, sp_artist, sp_album

    return None, None, None


def verify_albums(config, data_dir):
    analysis_dir = os.path.join(data_dir, "analysis")
    if not os.path.exists(analysis_dir):
        print("No analysis directory found.")
        return

    sp = get_spotify_client(config)
    analysis_files = sorted(f for f in os.listdir(analysis_dir) if f.endswith(".json"))

    total_albums = 0
    found_exact = 0
    found_fuzzy = 0
    not_found = 0
    corrections = []

    for filename in analysis_files:
        path = os.path.join(analysis_dir, filename)
        with open(path) as f:
            analysis = json.load(f)
        if not analysis.get("albums"):
            continue

        shortcode = filename.replace(".json", "")
        file_changed = False

        for album_info in analysis["albums"]:
            artist = album_info["artist"]
            album_name = album_info["album"]
            total_albums += 1

            result = search_album(sp, artist, album_name)
            if result:
                found_exact += 1
                continue

            match, correct_artist, correct_album = _fuzzy_find_album(sp, artist, album_name)
            if match:
                found_fuzzy += 1
                old = f"{artist} - {album_name}"
                new = f"{correct_artist} - {correct_album}"
                print(f"  FIX  {old}  ->  {new}")
                album_info["artist"] = correct_artist
                album_info["album"] = correct_album
                corrections.append((shortcode, old, new))
                file_changed = True
            else:
                not_found += 1
                print(f"  ???  {artist} - {album_name}")

        if file_changed:
            with open(path, "w") as f:
                json.dump(analysis, f, indent=2)

    print(f"\nVerified {total_albums} albums: {found_exact} exact, "
          f"{found_fuzzy} corrected, {not_found} not on Spotify")
    return {"total": total_albums, "exact": found_exact,
            "corrected": found_fuzzy, "not_found": not_found}


def create_playlists(config, data_dir):
    analysis_dir = os.path.join(data_dir, "analysis")
    playlists_dir = os.path.join(data_dir, "playlists")
    posts_dir = os.path.join(data_dir, "posts")
    os.makedirs(playlists_dir, exist_ok=True)

    if not os.path.exists(analysis_dir):
        print("No analysis directory found. Run analysis first.")
        return {"processed": 0, "skipped": 0, "failed": 0}

    analysis_files = sorted(f for f in os.listdir(analysis_dir) if f.endswith(".json"))
    sp = get_spotify_client(config)

    processed = 0
    skipped = 0
    failed = 0

    for i, filename in enumerate(analysis_files, 1):
        shortcode = filename.replace(".json", "")
        playlist_file = os.path.join(playlists_dir, filename)

        if os.path.exists(playlist_file):
            skipped += 1
            continue

        with open(os.path.join(analysis_dir, filename)) as f:
            analysis = json.load(f)

        if not analysis.get("albums"):
            skipped += 1
            continue

        metadata_path = os.path.join(posts_dir, shortcode, "metadata.json")
        caption_path = os.path.join(posts_dir, shortcode, "caption.txt")

        owner = shortcode
        date = ""
        caption = ""
        source = "instagram"
        if os.path.exists(metadata_path):
            with open(metadata_path) as f:
                meta = json.load(f)
            owner = meta.get("owner", shortcode)
            date = meta.get("timestamp", "")[:10]
            source = meta.get("source", "instagram")
        if os.path.exists(caption_path):
            with open(caption_path) as f:
                caption = f.read()

        try:
            genre = analysis.get("genre", "")
            genre_suffix = f" [{genre}]" if genre else ""
            playlist_name = f"@{owner}{genre_suffix}"
            description = caption[:300] if caption else ""
            token = sp.auth_manager.get_access_token(as_dict=False)
            resp = requests.post(
                "https://api.spotify.com/v1/me/playlists",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"name": playlist_name, "public": False, "description": description},
            )
            resp.raise_for_status()
            created = resp.json()
            playlist_id = created["id"]
            playlist_url = created["external_urls"]["spotify"]

            albums_added = []
            albums_not_found = []
            all_track_uris = []

            for album_info in analysis["albums"]:
                artist = album_info["artist"]
                album_name = album_info["album"]
                result = search_album(sp, artist, album_name)
                if result:
                    track_uris = get_album_track_uris(sp, result["id"])
                    all_track_uris.extend(track_uris)
                    albums_added.append({
                        "artist": artist,
                        "album": album_name,
                        "spotify_album_id": result["id"],
                    })
                else:
                    albums_not_found.append({"artist": artist, "album": album_name})
                    print(f"    Album not found: {artist} - {album_name}")

            if all_track_uris:
                add_tracks_batched(sp, playlist_id, all_track_uris)

            with open(playlist_file, "w") as f:
                json.dump({
                    "playlist_id": playlist_id,
                    "playlist_url": playlist_url,
                    "albums_added": albums_added,
                    "albums_not_found": albums_not_found,
                }, f, indent=2)

            processed += 1
            print(f"  Created playlist {i}/{len(analysis_files)}: {playlist_name} ({playlist_url})")
        except Exception as e:
            failed += 1
            print(f"  Failed {shortcode}: {e}")

    print(f"\nDone. Processed: {processed}, Skipped: {skipped}, Failed: {failed}")
    return {"processed": processed, "skipped": skipped, "failed": failed}
