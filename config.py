from dataclasses import dataclass
from dotenv import load_dotenv
import os


@dataclass
class Config:
    spotify_client_id: str
    spotify_client_secret: str
    spotify_redirect_uri: str
    qobuz_email: str = ""
    qobuz_password: str = ""
    qobuz_token: str = ""
    qobuz_user_id: str = ""


REQUIRED_KEYS = [
    "SPOTIFY_CLIENT_ID",
    "SPOTIFY_CLIENT_SECRET",
    "SPOTIFY_REDIRECT_URI",
]


def load_config(env_path=".env"):
    load_dotenv(env_path, override=True)
    missing = [k for k in REQUIRED_KEYS if not os.environ.get(k)]
    if missing:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing)}. "
            "Copy .env.example to .env and fill in your credentials."
        )
    return Config(
        spotify_client_id=os.environ["SPOTIFY_CLIENT_ID"],
        spotify_client_secret=os.environ["SPOTIFY_CLIENT_SECRET"],
        spotify_redirect_uri=os.environ["SPOTIFY_REDIRECT_URI"],
        qobuz_email=os.environ.get("QOBUZ_EMAIL", ""),
        qobuz_password=os.environ.get("QOBUZ_PASSWORD", ""),
        qobuz_token=os.environ.get("QOBUZ_TOKEN", ""),
        qobuz_user_id=os.environ.get("QOBUZ_USER_ID", ""),
    )
