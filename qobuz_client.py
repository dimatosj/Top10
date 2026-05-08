import json
import os

import requests
from qobuz_dl.bundle import Bundle


class QobuzClient:
    BASE = "https://www.qobuz.com/api.json/0.2/"

    def __init__(self, email=None, password=None, token=None, user_id=None):
        bundle = Bundle()
        self.app_id = str(bundle.get_app_id())
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:130.0) Gecko/20100101 Firefox/130.0",
            "X-App-Id": self.app_id,
        })
        if token and user_id:
            self._login_token(token, user_id)
        elif email and password:
            self._login(email, password)
        else:
            raise ValueError("Provide either token+user_id or email+password")

    def _login_token(self, token, user_id):
        self.user_auth_token = token
        self.user_id = user_id
        self.session.headers.update({"X-User-Auth-Token": token})
        r = self.session.get(self.BASE + "user/get", params={
            "user_id": user_id,
        })
        r.raise_for_status()

    def _login(self, email, password):
        r = self.session.get(self.BASE + "user/login", params={
            "email": email, "password": password, "app_id": self.app_id,
        })
        r.raise_for_status()
        data = r.json()
        self.user_auth_token = data["user_auth_token"]
        self.session.headers.update({"X-User-Auth-Token": self.user_auth_token})
        self.user_id = data["user"]["id"]

    def _get(self, endpoint, **params):
        r = self.session.get(self.BASE + endpoint, params=params)
        r.raise_for_status()
        return r.json()

    def _post(self, endpoint, **params):
        r = self.session.post(self.BASE + endpoint, params=params)
        r.raise_for_status()
        return r.json()

    def search_album(self, artist, album):
        query = f"{artist} {album}"
        data = self._get("album/search", query=query, limit=5)
        for item in data.get("albums", {}).get("items", []):
            return item
        return None

    def get_album_genre(self, album_id):
        data = self._get("album/get", album_id=album_id)
        genre = data.get("genre", {})
        return genre.get("name", "")

    def get_album_track_ids(self, album_id):
        data = self._get("album/get", album_id=album_id)
        tracks = data.get("tracks", {}).get("items", [])
        return [str(t["id"]) for t in tracks]

    def create_playlist(self, name, description=""):
        data = self._post("playlist/create",
                          name=name, description=description[:300],
                          is_public="false", app_id=self.app_id)
        return data["id"], data.get("url", "")

    def add_tracks(self, playlist_id, track_ids):
        if not track_ids:
            return
        self._post("playlist/addTracks",
                    playlist_id=playlist_id,
                    track_ids=",".join(track_ids),
                    playlist_track_ids=",".join(track_ids))


def derive_genres(config, data_dir):
    analysis_dir = os.path.join(data_dir, "analysis")
    if not os.path.exists(analysis_dir):
        print("No analysis directory found.")
        return

    print("Logging in to Qobuz...")
    qb = _make_client(config)
    print("Logged in.")

    from collections import Counter

    analysis_files = sorted(f for f in os.listdir(analysis_dir) if f.endswith(".json"))
    updated = 0

    for filename in analysis_files:
        path = os.path.join(analysis_dir, filename)
        with open(path) as f:
            analysis = json.load(f)
        if not analysis.get("albums"):
            continue
        if analysis.get("genre"):
            continue

        genres = Counter()
        for album_info in analysis["albums"]:
            result = qb.search_album(album_info["artist"], album_info["album"])
            if result:
                genre = qb.get_album_genre(result["id"])
                if genre:
                    genres[genre] += 1

        if genres:
            top_genre = genres.most_common(1)[0][0]
            analysis["genre"] = top_genre
            with open(path, "w") as f:
                json.dump(analysis, f, indent=2)
            updated += 1
            print(f"  {filename}: {top_genre} ({dict(genres)})")

    print(f"\nTagged {updated} analysis files with genres.")


def _make_client(config):
    if config.qobuz_token and config.qobuz_user_id:
        return QobuzClient(token=config.qobuz_token, user_id=config.qobuz_user_id)
    if config.qobuz_email and config.qobuz_password:
        return QobuzClient(email=config.qobuz_email, password=config.qobuz_password)
    raise ValueError(
        "Set QOBUZ_TOKEN + QOBUZ_USER_ID in .env (from play.qobuz.com DevTools → "
        "Application → Local Storage → localuser), or QOBUZ_EMAIL + QOBUZ_PASSWORD."
    )


def create_qobuz_playlists(config, data_dir):
    analysis_dir = os.path.join(data_dir, "analysis")
    playlists_dir = os.path.join(data_dir, "playlists")
    posts_dir = os.path.join(data_dir, "posts")
    os.makedirs(playlists_dir, exist_ok=True)

    if not os.path.exists(analysis_dir):
        print("No analysis directory found. Run analysis first.")
        return {"processed": 0, "skipped": 0, "failed": 0}

    print("Logging in to Qobuz...")
    qb = _make_client(config)
    print("Logged in.")

    analysis_files = sorted(f for f in os.listdir(analysis_dir) if f.endswith(".json"))

    processed = 0
    skipped = 0
    failed = 0

    for i, filename in enumerate(analysis_files, 1):
        shortcode = filename.replace(".json", "")
        playlist_file = os.path.join(playlists_dir, filename)

        if os.path.exists(playlist_file):
            existing = json.load(open(playlist_file))
            if existing.get("qobuz_playlist_id"):
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

            playlist_id, playlist_url = qb.create_playlist(playlist_name, caption)

            albums_added = []
            albums_not_found = []
            all_track_ids = []

            for album_info in analysis["albums"]:
                artist = album_info["artist"]
                album_name = album_info["album"]
                result = qb.search_album(artist, album_name)
                if result:
                    track_ids = qb.get_album_track_ids(result["id"])
                    all_track_ids.extend(track_ids)
                    albums_added.append({
                        "artist": artist,
                        "album": album_name,
                        "qobuz_album_id": str(result["id"]),
                    })
                else:
                    albums_not_found.append({"artist": artist, "album": album_name})
                    print(f"    Album not found: {artist} - {album_name}")

            if all_track_ids:
                qb.add_tracks(playlist_id, all_track_ids)

            # Merge with existing playlist data (Spotify may already be there)
            playlist_data = {}
            if os.path.exists(playlist_file):
                with open(playlist_file) as f:
                    playlist_data = json.load(f)

            playlist_data.update({
                "qobuz_playlist_id": str(playlist_id),
                "qobuz_albums_added": albums_added,
                "qobuz_albums_not_found": albums_not_found,
            })

            with open(playlist_file, "w") as f:
                json.dump(playlist_data, f, indent=2)

            processed += 1
            print(f"  Created Qobuz playlist {i}/{len(analysis_files)}: {playlist_name}")
        except Exception as e:
            failed += 1
            print(f"  Failed {shortcode}: {e}")

    print(f"\nDone. Processed: {processed}, Skipped: {skipped}, Failed: {failed}")
    return {"processed": processed, "skipped": skipped, "failed": failed}


def verify_qobuz_albums(config, data_dir):
    analysis_dir = os.path.join(data_dir, "analysis")
    if not os.path.exists(analysis_dir):
        print("No analysis directory found.")
        return

    print("Logging in to Qobuz...")
    qb = _make_client(config)
    print("Logged in.")

    analysis_files = sorted(f for f in os.listdir(analysis_dir) if f.endswith(".json"))

    total = 0
    found = 0
    not_found = 0

    for filename in analysis_files:
        with open(os.path.join(analysis_dir, filename)) as f:
            analysis = json.load(f)
        if not analysis.get("albums"):
            continue

        for album_info in analysis["albums"]:
            artist = album_info["artist"]
            album_name = album_info["album"]
            total += 1
            result = qb.search_album(artist, album_name)
            if result:
                found += 1
            else:
                not_found += 1
                print(f"  ???  {artist} - {album_name}")

    print(f"\nQobuz: {found}/{total} albums found, {not_found} missing")
