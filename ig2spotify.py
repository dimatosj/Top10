import os
import click


@click.group()
@click.option("--data-dir", default="./data", help="Directory for all intermediate data")
@click.pass_context
def cli(ctx, data_dir):
    ctx.ensure_object(dict)
    ctx.obj["data_dir"] = os.path.abspath(data_dir)


@cli.command()
@click.option("--username", required=True, help="Instagram username")
@click.pass_context
def download(ctx, username):
    """Download saved videos from Instagram."""
    from downloader import download_saved
    download_saved(username=username, data_dir=ctx.obj["data_dir"])


@cli.command()
@click.pass_context
def extract(ctx):
    """Extract audio from downloaded videos using ffmpeg."""
    from extractor import extract_all_audio
    extract_all_audio(data_dir=ctx.obj["data_dir"])


@cli.command()
@click.pass_context
def playlist(ctx):
    """Create Spotify playlists from analysis results."""
    from config import load_config
    from spotify_client import create_playlists
    cfg = load_config()
    create_playlists(config=cfg, data_dir=ctx.obj["data_dir"])


@cli.command()
@click.option("--username", required=True, help="Instagram username")
@click.pass_context
def run(ctx, username):
    """Run download + extract in sequence."""
    ctx.invoke(download, username=username)
    ctx.invoke(extract)
    click.echo("\nAudio extracted. Ask Claude Code to analyze the posts, then run:")
    click.echo(f"  python ig2spotify.py playlist --data-dir {ctx.obj['data_dir']}")


@cli.command("fb-download")
@click.option("--export-path", required=True, help="Path to Facebook DYI export directory")
@click.option("--browser", default="chrome", help="Browser to extract cookies from")
@click.pass_context
def fb_download(ctx, export_path, browser):
    """Download saved videos from Facebook export."""
    from fb_downloader import download_facebook_saved
    download_facebook_saved(
        export_path=export_path,
        data_dir=ctx.obj["data_dir"],
        browser=browser,
    )


@cli.command("fb-run")
@click.option("--export-path", required=True, help="Path to Facebook DYI export directory")
@click.option("--browser", default="chrome", help="Browser to extract cookies from")
@click.pass_context
def fb_run(ctx, export_path, browser):
    """Run fb-download + extract in sequence."""
    ctx.invoke(fb_download, export_path=export_path, browser=browser)
    ctx.invoke(extract)
    click.echo("\nAudio extracted. Ask Claude Code to analyze the posts, then run:")
    click.echo(f"  python ig2spotify.py playlist --data-dir {ctx.obj['data_dir']}")


if __name__ == "__main__":
    cli()
