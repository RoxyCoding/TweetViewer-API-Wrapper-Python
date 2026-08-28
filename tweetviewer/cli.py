"""Command-line interface for TweetViewerClient."""

from __future__ import annotations

import argparse
import json
from typing import Any, Optional

from .client import TweetViewerClient, TweetViewerError


def _print(data: Any) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tweetviewer-py")
    subparsers = parser.add_subparsers(dest="command", required=True)

    profile = subparsers.add_parser("profile")
    profile.add_argument("handle")

    timeline = subparsers.add_parser("timeline")
    timeline.add_argument("handle")
    timeline.add_argument("--cursor")

    latest = subparsers.add_parser("latest")
    latest.add_argument("handle")
    latest.add_argument("--exclude-replies", action="store_true")
    latest.add_argument("--exclude-retweets", action="store_true")

    tweet = subparsers.add_parser("tweet")
    tweet.add_argument("id_or_url")

    resolve = subparsers.add_parser("resolve")
    resolve.add_argument("id_or_url")
    resolve.add_argument("--lang", default="en")

    view = subparsers.add_parser("view")
    view.add_argument("query", nargs="+")

    download = subparsers.add_parser("download")
    download.add_argument("media_url")
    download.add_argument("output")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    client = TweetViewerClient()
    try:
        if args.command == "profile":
            result = client.get_profile(args.handle)
        elif args.command == "timeline":
            result = client.get_timeline(args.handle, cursor=args.cursor)
        elif args.command == "latest":
            result = client.get_latest_tweet(
                args.handle,
                include_replies=not args.exclude_replies,
                include_retweets=not args.exclude_retweets,
            )
        elif args.command == "tweet":
            result = client.get_tweet(args.id_or_url)
        elif args.command == "resolve":
            result = client.resolve_media(args.id_or_url, language=args.lang)
        elif args.command == "view":
            result = client.view(" ".join(args.query))
        else:
            path = client.download_media(args.media_url, args.output)
            result = {"ok": True, "path": str(path.resolve())}
        _print(result)
        return 0
    except TweetViewerError as error:
        _print({"ok": False, "status": error.status, "code": error.code, "error": str(error)})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

