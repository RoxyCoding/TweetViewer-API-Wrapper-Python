"""Synchronous Tweet Viewer client implemented with the Python standard library."""

from __future__ import annotations

import json
import re
import shutil
import socket
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, BinaryIO, Dict, Generator, Iterable, Mapping, Optional, Union
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urljoin, urlparse
from urllib.request import OpenerDirector, Request, build_opener

DEFAULT_BASE_URL = "https://tweetviewer.com/"
DEFAULT_LIVE_BASE_URL = "https://api.fxtwitter.com/"
DEFAULT_TIMEOUT = 15.0


class TweetViewerError(Exception):
    """Tweet Viewer API or transport error."""

    def __init__(
        self,
        message: str,
        *,
        status: Optional[int] = None,
        code: Optional[str] = None,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.details = details


def normalize_handle(value: str) -> str:
    """Extract and validate an X handle from a handle or profile URL."""

    if not isinstance(value, str) or not value.strip():
        raise TweetViewerError("Xのユーザー名を指定してください。", code="INVALID_HANDLE")

    handle = value.strip()
    parsed = urlparse(handle)
    hostname = (parsed.hostname or "").lower()
    parts = [part for part in parsed.path.split("/") if part]

    if parsed.scheme and hostname in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}:
        handle = parts[0] if parts else ""
    elif parsed.scheme and hostname in {"tweetviewer.com", "www.tweetviewer.com"}:
        try:
            handle = parts[parts.index("twitter-viewer") + 1]
        except (ValueError, IndexError):
            handle = ""
    else:
        handle = re.sub(r"^@", "", handle)

    if not re.fullmatch(r"[A-Za-z0-9_]{2,15}", handle):
        raise TweetViewerError(
            "Xのユーザー名は2〜15文字の英数字またはアンダースコアで指定してください。",
            code="INVALID_HANDLE",
        )
    return handle


def normalize_tweet_id(value: Union[str, int]) -> str:
    """Extract and validate a tweet ID from an ID or status URL."""

    text = str(value).strip()
    match = re.search(r"(?:status|statuses)/(\d{15,25})(?:\b|/|\?|#)", text, re.IGNORECASE)
    tweet_id = match.group(1) if match else text
    if not re.fullmatch(r"\d{15,25}", tweet_id):
        raise TweetViewerError(
            "15〜25桁のツイートID、またはXの投稿URLを指定してください。",
            code="INVALID_TWEET_ID",
        )
    return tweet_id


def _avatar_url(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    return re.sub(r"_(?:normal|200x200)(\.[a-z]+)(\?.*)?$", r"_400x400\1\2", value, flags=re.IGNORECASE)


def _without_none(values: Mapping[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}


def _live_profile(author: Mapping[str, Any], fallback_handle: str) -> Dict[str, Any]:
    verification = author.get("verification") or {}
    website = author.get("website")
    if isinstance(website, Mapping):
        website = website.get("url")
    handle = author.get("screen_name") or fallback_handle
    raw_description = author.get("raw_description") or {}
    return _without_none(
        {
            "handle": handle,
            "displayName": author.get("name") or handle,
            "bio": author.get("description") or raw_description.get("text") or "",
            "avatar": _avatar_url(author.get("avatar_url")),
            "banner": author.get("banner_url"),
            "followers": author.get("followers"),
            "following": author.get("following"),
            "posts": author.get("statuses"),
            "joined": author.get("joined"),
            "location": author.get("location"),
            "website": website,
            "verified": bool(verification.get("verified")),
            "isBlueVerified": verification.get("type") == "blue",
            "profileUrl": author.get("url") or f"https://x.com/{handle}",
        }
    )


def _live_media(items: Optional[Iterable[Mapping[str, Any]]]) -> list[Dict[str, Any]]:
    result: list[Dict[str, Any]] = []
    for item in items or []:
        source_type = item.get("type")
        media_type = "video" if source_type == "video" else "animated_gif" if source_type in {"gif", "animated_gif"} else "photo"
        thumbnail = item.get("thumbnail_url") or item.get("url")
        media = _without_none(
            {
                "type": media_type,
                "url": item.get("url") if media_type == "photo" else thumbnail,
                "thumb": thumbnail,
                "width": item.get("width"),
                "height": item.get("height"),
            }
        )
        if media_type != "photo":
            formats = [
                item_format
                for item_format in (item.get("formats") or [])
                if item_format.get("container") == "mp4" and isinstance(item_format.get("url"), str)
            ]
            formats.sort(key=lambda item_format: item_format.get("bitrate") or 0, reverse=True)
            duration = item.get("duration")
            media["video"] = _without_none(
                {
                    "mp4": formats[0].get("url") if formats else item.get("url"),
                    "poster": thumbnail,
                    "duration_ms": round(duration * 1000) if isinstance(duration, (int, float)) else None,
                }
            )
        result.append(media)
    return result


def _live_tweet(tweet: Mapping[str, Any]) -> Dict[str, Any]:
    author = tweet.get("author") or {}
    reposted_by = tweet.get("reposted_by")
    replying_to = tweet.get("replying_to")
    tweet_id = str(tweet.get("id") or "")
    raw_text = tweet.get("raw_text") or {}
    created_at = tweet.get("created_at")
    if not created_at and tweet.get("created_timestamp"):
        created_at = datetime.fromtimestamp(tweet["created_timestamp"], tz=timezone.utc).isoformat().replace("+00:00", "Z")
    author_handle = author.get("screen_name")
    reply_handle = replying_to.get("screen_name") if isinstance(replying_to, Mapping) else None
    return _without_none(
        {
            "id": tweet_id,
            "createdAt": created_at or "",
            "text": tweet.get("text") or raw_text.get("text") or "",
            "permalink": tweet.get("url") or f"https://x.com/{author_handle or 'i'}/status/{tweet_id}",
            "replies": tweet.get("replies") or 0,
            "retweets": tweet.get("reposts") or 0,
            "likes": tweet.get("likes") or 0,
            "views": tweet.get("views"),
            "quotes": tweet.get("quotes"),
            "bookmarks": tweet.get("bookmarks"),
            "media": _live_media((tweet.get("media") or {}).get("all")),
            "isRetweet": bool(reposted_by),
            "retweetedBy": reposted_by.get("screen_name") if isinstance(reposted_by, Mapping) else None,
            "retweetedByName": reposted_by.get("name") if isinstance(reposted_by, Mapping) else None,
            "isReply": bool(replying_to),
            "isSelfReply": bool(reply_handle and author_handle and reply_handle.lower() == author_handle.lower()),
            "sensitive": bool(tweet.get("possibly_sensitive")),
            "authorName": author.get("name") or author_handle,
            "authorHandle": author_handle,
            "authorAvatar": _avatar_url(author.get("avatar_url")),
            "authorVerified": bool((author.get("verification") or {}).get("verified")),
        }
    )


def _tweet_time(tweet: Mapping[str, Any]) -> float:
    value = tweet.get("createdAt")
    if not isinstance(value, str) or not value:
        return float("-inf")
    try:
        return parsedate_to_datetime(value).timestamp()
    except (TypeError, ValueError, OverflowError):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
        except (TypeError, ValueError, OverflowError):
            return float("-inf")


class TweetViewerClient:
    """Client for Tweet Viewer endpoints and its live timeline provider."""

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        live_base_url: str = DEFAULT_LIVE_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT,
        headers: Optional[Mapping[str, str]] = None,
        opener: Optional[OpenerDirector] = None,
    ) -> None:
        if not isinstance(timeout, (int, float)) or timeout <= 0:
            raise TypeError("timeout must be a positive number")
        self.base_url = base_url.rstrip("/") + "/"
        self.live_base_url = live_base_url.rstrip("/") + "/"
        self.timeout = float(timeout)
        self.headers = dict(headers or {})
        self.opener = opener or build_opener()

    def view(self, query: str) -> Dict[str, Any]:
        if not isinstance(query, str) or not query.strip():
            raise TweetViewerError("検索文字列を指定してください。", code="INVALID_QUERY")
        result = self._request_json(
            "api/twitter/view",
            method="POST",
            body=json.dumps({"q": query.strip()}, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        if result.get("kind") not in {"profile", "tweet"}:
            raise self._unexpected(result)
        return result

    def get_profile(self, handle: str) -> Dict[str, Any]:
        result = self.view(normalize_handle(handle))
        if result.get("kind") != "profile":
            raise TweetViewerError(
                "プロフィールレスポンスではありません。",
                code="UNEXPECTED_RESPONSE",
                details=result,
            )
        return result

    def get_timeline(self, handle: str, *, cursor: Optional[str] = None) -> Dict[str, Any]:
        normalized = normalize_handle(handle)
        path = f"2/profile/{quote(normalized, safe='')}/statuses"
        if cursor:
            path += "?" + urlencode({"cursor": cursor})
        data = self._request_json(
            path,
            base_url=self.live_base_url,
            include_default_headers=False,
            require_ok=False,
            invalid_json_code="INVALID_LIVE_JSON",
            invalid_json_message="ライブタイムラインからJSON以外のレスポンスが返されました。",
        )
        if data.get("_http_status", 500) >= 400 or data.get("code") != 200 or not isinstance(data.get("results"), list):
            raise TweetViewerError(
                data.get("message") or "Live timeline API error",
                status=data.get("_http_status"),
                code="LIVE_API_ERROR",
                details=data,
            )

        results = data["results"]
        author = next(
            (
                tweet.get("author")
                for tweet in results
                if isinstance(tweet, Mapping)
                and isinstance(tweet.get("author"), Mapping)
                and str(tweet["author"].get("screen_name", "")).lower() == normalized.lower()
            ),
            None,
        )
        if author is None and results and isinstance(results[0], Mapping):
            author = results[0].get("author")

        response: Dict[str, Any] = {
            "ok": True,
            "source": "fxtwitter-v2-live",
            "tweets": [_live_tweet(tweet) for tweet in results if isinstance(tweet, Mapping)],
            "cursor": (data.get("cursor") or {}).get("bottom"),
        }
        if isinstance(author, Mapping):
            response["profile"] = _live_profile(author, normalized)
        return response

    def get_live_timeline(self, handle: str, *, cursor: Optional[str] = None) -> Dict[str, Any]:
        """Compatibility alias. Timeline access is always live-only."""

        return self.get_timeline(handle, cursor=cursor)

    def get_latest_tweet(
        self,
        handle: str,
        *,
        include_replies: bool = True,
        include_retweets: bool = True,
    ) -> Dict[str, Any]:
        timeline = self.get_timeline(handle)
        tweets = [
            tweet
            for tweet in timeline["tweets"]
            if (include_replies or not tweet.get("isReply"))
            and (include_retweets or not tweet.get("isRetweet"))
        ]
        if not tweets:
            raise TweetViewerError("取得できる投稿がありません。", code="NO_TWEETS")
        return max(tweets, key=_tweet_time)

    def iterate_timeline(
        self,
        handle: str,
        *,
        cursor: Optional[str] = None,
        max_pages: Optional[int] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        if max_pages is not None and max_pages <= 0:
            raise ValueError("max_pages must be greater than zero")
        page_number = 0
        current_cursor = cursor
        while max_pages is None or page_number < max_pages:
            page = self.get_timeline(handle, cursor=current_cursor)
            yield page
            page_number += 1
            next_cursor = page.get("cursor")
            if not next_cursor or next_cursor == current_cursor:
                return
            current_cursor = next_cursor

    def get_tweet(self, value: Union[str, int]) -> Dict[str, Any]:
        path = "api/twitter/tweet?" + urlencode({"id": normalize_tweet_id(value)})
        result = self._request_json(path)
        if not isinstance(result.get("tweet"), Mapping) or not isinstance(result["tweet"].get("id"), str):
            raise self._unexpected(result)
        return result

    def resolve_media(self, value: Union[str, int], *, language: str = "en") -> Dict[str, Any]:
        tweet_id = normalize_tweet_id(value)
        if not re.fullmatch(r"[A-Za-z]{2}(?:-[A-Za-z]{2})?", language):
            raise TweetViewerError(
                "languageはenまたはja-JPのような言語コードで指定してください。",
                code="INVALID_LANGUAGE",
            )
        path = "api/resolve?" + urlencode(
            {"url": f"https://x.com/i/status/{tweet_id}", "lang": language.lower()}
        )
        result = self._request_json(path)
        if result.get("kind") not in {"video", "photo", "text"} or not isinstance(result.get("variants"), list):
            raise self._unexpected(result)
        return result

    def fetch_media(self, media_url: str, *, byte_range: Optional[str] = None) -> BinaryIO:
        parsed = urlparse(str(media_url))
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise TweetViewerError("HTTPまたはHTTPSのメディアURLを指定してください。", code="INVALID_MEDIA_URL")
        if byte_range and not re.fullmatch(r"bytes=\d*-\d*(?:,\s*\d*-\d*)*", byte_range):
            raise TweetViewerError("byte_rangeはbytes=0-1023の形式で指定してください。", code="INVALID_RANGE")

        path = "api/file?" + urlencode({"url": media_url})
        headers = {"Accept": "*/*"}
        if byte_range:
            headers["Range"] = byte_range
        response = self._open(path, headers=headers)
        status = getattr(response, "status", None) or response.getcode()
        if status >= 400:
            body = response.read(500).decode("utf-8", "replace")
            response.close()
            raise TweetViewerError(
                body or f"Tweet Viewer file API error ({status})",
                status=status,
                code="FILE_API_ERROR",
                details=body,
            )
        return response

    def download_media(
        self,
        media_url: str,
        destination: Union[str, Path],
        *,
        byte_range: Optional[str] = None,
    ) -> Path:
        """Download proxied media to a local file and return its Path."""

        target = Path(destination)
        with self.fetch_media(media_url, byte_range=byte_range) as response, target.open("wb") as output:
            shutil.copyfileobj(response, output)
        return target

    def _unexpected(self, details: Any) -> TweetViewerError:
        return TweetViewerError(
            "Tweet Viewerのレスポンス形式が変更された可能性があります。",
            code="UNEXPECTED_RESPONSE",
            details=details,
        )

    def _request_json(
        self,
        path: str,
        *,
        method: str = "GET",
        body: Optional[bytes] = None,
        headers: Optional[Mapping[str, str]] = None,
        base_url: Optional[str] = None,
        include_default_headers: bool = True,
        require_ok: bool = True,
        invalid_json_code: str = "INVALID_JSON",
        invalid_json_message: str = "Tweet ViewerからJSON以外のレスポンスが返されました。",
    ) -> Dict[str, Any]:
        response = self._open(
            path,
            method=method,
            body=body,
            headers=headers,
            base_url=base_url,
            include_default_headers=include_default_headers,
        )
        try:
            status = getattr(response, "status", None) or response.getcode()
            text = response.read().decode("utf-8", "replace")
        finally:
            response.close()
        try:
            data = json.loads(text) if text else None
        except json.JSONDecodeError as error:
            raise TweetViewerError(
                invalid_json_message,
                status=status,
                code=invalid_json_code,
                details=text[:500],
            ) from error
        if not isinstance(data, dict):
            raise TweetViewerError(
                invalid_json_message,
                status=status,
                code=invalid_json_code,
                details=text[:500],
            )
        if not require_ok:
            data["_http_status"] = status
            return data
        if status >= 400 or data.get("ok") is not True:
            raise TweetViewerError(
                data.get("error") or f"Tweet Viewer API error ({status})",
                status=status,
                code=data.get("code") or "API_ERROR",
                details=data,
            )
        return data

    def _open(
        self,
        path: str,
        *,
        method: str = "GET",
        body: Optional[bytes] = None,
        headers: Optional[Mapping[str, str]] = None,
        base_url: Optional[str] = None,
        include_default_headers: bool = True,
    ) -> BinaryIO:
        url = urljoin(base_url or self.base_url, path)
        request_headers = dict(self.headers) if include_default_headers else {}
        request_headers.update(headers or {})
        if not any(name.lower() == "accept" for name in request_headers):
            request_headers["Accept"] = "application/json"
        request = Request(url, data=body, headers=request_headers, method=method)
        try:
            return self.opener.open(request, timeout=self.timeout)
        except HTTPError as error:
            return error
        except (URLError, socket.timeout, TimeoutError, OSError) as error:
            reason = getattr(error, "reason", error)
            timed_out = isinstance(reason, (socket.timeout, TimeoutError))
            raise TweetViewerError(
                "Tweet Viewerへの接続がタイムアウトしました。" if timed_out else "Tweet Viewerへの接続に失敗しました。",
                code="ABORTED" if timed_out else "NETWORK_ERROR",
            ) from error
