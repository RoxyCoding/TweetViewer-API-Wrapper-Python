# TweetViewer API Wrapper — Python

X（旧Twitter）の公開プロフィール・タイムライン・ツイート・メディアを取得するための非公式Pythonクライアントです。標準ライブラリのみで動作し、追加の依存関係はありません。

- **Pythonライブラリ** — `TweetViewerClient`
- **CLI** — `python3 -m tweetviewer <command>`
- **ローカルREST API** — `python3 -m tweetviewer.server`

## 必要環境

- Python 3.10 以上
- 追加依存パッケージなし

## インストール

```bash
pip install -e .
```

インストールすると `tweetviewer-py` / `tweetviewer-server-py` コマンドが使えます。インストールせずリポジトリ直下から `python3 -m tweetviewer ...` として実行することもできます。

## Pythonから使う

```python
from tweetviewer import TweetViewerClient

client = TweetViewerClient()

profile = client.get_profile("@RoxyCoding")
print(profile["displayName"], profile.get("followers"))

page = client.get_timeline("RoxyCoding")
print(page["tweets"])

latest = client.get_latest_tweet("RoxyCoding")
print(latest["text"])

for page in client.iterate_timeline("RoxyCoding", max_pages=3):
    for tweet in page["tweets"]:
        print(tweet["id"], tweet["text"])
```

画像や動画を保存する場合:

```python
media = client.resolve_media("https://x.com/RoxyCoding/status/2092592498862641403")
client.download_media(media["variants"][0]["url"], "downloaded-media.bin")
```

### 主なメソッド

| メソッド | 説明 |
| --- | --- |
| `view(query)` | ハンドル／URL／ツイートIDを判別して取得 |
| `get_profile(handle)` | プロフィール情報 |
| `get_timeline(handle, cursor=None)` | タイムライン1ページ分 |
| `get_live_timeline(handle, cursor=None)` | ライブ提供元からのタイムライン |
| `iterate_timeline(handle, max_pages=...)` | ページを順に辿るジェネレータ |
| `get_latest_tweet(handle, include_replies=, include_retweets=)` | 最新ツイート1件 |
| `get_tweet(id_or_url)` | 単一ツイート |
| `resolve_media(id_or_url, language="en")` | メディアURLの解決 |
| `fetch_media(media_url, byte_range=None)` | メディアをストリームで取得 |
| `download_media(media_url, path)` | メディアをファイルに保存 |

### クライアントの設定

```python
client = TweetViewerClient(
    base_url="https://tweetviewer.com/",
    live_base_url="https://api.fxtwitter.com/",
    timeout=15.0,
    headers={"User-Agent": "my-app/1.0"},
)
```

### エラー処理

API・通信のエラーはすべて `TweetViewerError` として送出されます。`status` / `code` / `details` 属性から詳細を参照できます。

```python
from tweetviewer import TweetViewerClient, TweetViewerError

try:
    client.get_profile("存在しないハンドル")
except TweetViewerError as error:
    print(error, error.status, error.code)
```

## CLI

```bash
python3 -m tweetviewer profile RoxyCoding
python3 -m tweetviewer timeline RoxyCoding [--cursor CURSOR]
python3 -m tweetviewer latest RoxyCoding [--exclude-replies] [--exclude-retweets]
python3 -m tweetviewer tweet 2092592498862641403
python3 -m tweetviewer resolve 2092592498862641403 [--lang en]
python3 -m tweetviewer view 'RoxyCoding'
python3 -m tweetviewer download '取得したメディアURL' image.png
```

結果はJSONで標準出力に出ます。

## ローカルREST API

Node.js版の3000番と同時に使えるよう、Python版の既定ポートは `3001` です。

```bash
python3 -m tweetviewer.server                 # 127.0.0.1:3001
python3 -m tweetviewer.server --port 3100     # ポート変更
python3 -m tweetviewer.server --host 0.0.0.0  # 待ち受けホスト変更
```

`HOST` / `PORT` 環境変数でも指定できます。

### エンドポイント

| メソッド | パス | 説明 |
| --- | --- | --- |
| GET | `/health` | ヘルスチェック |
| GET | `/v1/profiles/{handle}` | プロフィール |
| GET | `/v1/profiles/{handle}/timeline?cursor=` | タイムライン |
| GET | `/v1/profiles/{handle}/latest?includeReplies=1&includeRetweets=1` | 最新ツイート |
| GET | `/v1/tweets/{id}` | 単一ツイート |
| GET | `/v1/media/resolve?url=&lang=en` | メディアURLの解決 |
| GET | `/v1/media/file?url=` | メディアのストリーム配信 |
| POST | `/v1/view` | `{"q": "..."}` を判別して取得 |

```bash
curl -s localhost:3001/health | jq
curl -s localhost:3001/v1/profiles/RoxyCoding | jq
curl -s localhost:3001/v1/profiles/RoxyCoding/timeline | jq '.tweets[0]'
curl -s localhost:3001/v1/profiles/RoxyCoding/latest | jq '.tweet'
curl -s localhost:3001/v1/tweets/2092592498862641403 | jq
curl -s -X POST localhost:3001/v1/view \
  -H 'Content-Type: application/json' \
  -d '{"q":"RoxyCoding"}' | jq
```

## テスト

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q tweetviewer tests
```

## 注意

> Tweet Viewer、FxTwitter、X Corp.とは無関係の非公式クライアントです。公開コンテンツだけを対象にし、各サービスの利用規約、著作権、アクセス負荷を考慮して利用してください。
