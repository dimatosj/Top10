import json
import os
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
    user_id = sp.current_user()["id"]

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
            if source == "facebook":
                playlist_name = f"FB: {date}"
            else:
                playlist_name = f"IG: @{owner} - {date}"
            description = caption[:300] if caption else ""
            created = sp.user_playlist_create(
                user=user_id,
                name=playlist_name,
                public=False,
                description=description,
            )
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
