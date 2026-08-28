"""Unofficial Tweet Viewer API client."""

from .client import (
    TweetViewerClient,
    TweetViewerError,
    normalize_handle,
    normalize_tweet_id,
)

__all__ = [
    "TweetViewerClient",
    "TweetViewerError",
    "normalize_handle",
    "normalize_tweet_id",
    "tweet_viewer",
]

tweet_viewer = TweetViewerClient()

