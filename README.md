# Tweet Viewer API Wrapper — Python

Node.js版を残したまま移植した、Python 3.10以上向けの非公式Tweet Viewer APIクライアントです。外部パッケージは使わず、Python標準ライブラリだけで動作します。

タイムラインはリアルタイム専用です。`get_timeline()`、`iterate_timeline()`、`get_latest_tweet()`はTweet Viewerのページと同じライブ取得先（FxTwitter）を利用し、ローカルの5分キャッシュ処理はありません。ただし、取得先サービス側のキャッシュや反映遅延は制御できません。

> Tweet Viewer、FxTwitter、X Corp.とは無関係の非公式クライアントです。公開コンテンツだけを対象にし、各サービスの利用規約、著作権、アクセス負荷を考慮して利用してください。

## インストール

```bash
cd '/Users/kotohasaki/Documents/プログラミング2026/8/Tweet-Viewer-API-Wrapper-Python'
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

インストールしなくても、プロジェクトディレクトリ内で`python3 -m tweetviewer`を実行できます。

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

## CLI

```bash
python3 -m tweetviewer profile RoxyCoding
python3 -m tweetviewer timeline RoxyCoding
python3 -m tweetviewer latest RoxyCoding
python3 -m tweetviewer tweet 2092592498862641403
python3 -m tweetviewer resolve 2092592498862641403
python3 -m tweetviewer download '取得したメディアURL' image.png
```

## ローカルREST API

Node.js版の3000番と同時に使えるよう、Python版の既定ポートは`3001`です。

```bash
python3 -m tweetviewer.server
```

```bash
curl -s localhost:3001/health | jq
curl -s localhost:3001/v1/profiles/RoxyCoding/timeline | jq '.tweets[0]'
curl -s localhost:3001/v1/profiles/RoxyCoding/latest | jq '.tweet'
curl -s localhost:3001/v1/profiles/RoxyCoding | jq
curl -s localhost:3001/v1/tweets/2092592498862641403 | jq
```

ポートを変更する場合:

```bash
python3 -m tweetviewer.server --port 3100
```

## テスト

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q tweetviewer tests
```

