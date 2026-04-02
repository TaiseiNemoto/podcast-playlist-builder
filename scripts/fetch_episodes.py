import argparse
import base64
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, parse, request


TOKEN_URL = "https://accounts.spotify.com/api/token"
API_BASE_URL = "https://api.spotify.com/v1"


def require_env(name: str) -> str:
    # `name: str` と `-> str` は型ヒント。実行を強制はしないが、読み手に意図を伝えやすい。
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"環境変数 {name} が設定されていません。")
    return value


def request_access_token(client_id: str, client_secret: str) -> str:
    # f文字列は `f"...{変数}..."` の形で文字列へ値を埋め込める。
    credentials = f"{client_id}:{client_secret}".encode("utf-8")
    basic_token = base64.b64encode(credentials).decode("ascii")
    body = parse.urlencode({"grant_type": "client_credentials"}).encode("utf-8")
    req = request.Request(
        TOKEN_URL,
        data=body,
        headers={
            "Authorization": f"Basic {basic_token}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    return fetch_json(req)["access_token"]


def fetch_json(req: request.Request) -> dict[str, Any]:
    try:
        # `with` を使うと、ブロックを抜けるときにリソースが自動でクローズされる。
        with request.urlopen(req) as res:
            return json.loads(res.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Spotify API 呼び出しに失敗しました: HTTP {exc.code}\n{detail}"
        ) from exc
    except error.URLError as exc:
        raise RuntimeError(f"Spotify API へ接続できませんでした: {exc.reason}") from exc


def api_get(path: str, access_token: str, params: dict[str, Any]) -> dict[str, Any]:
    query = parse.urlencode(params)
    url = f"{API_BASE_URL}{path}?{query}"
    req = request.Request(
        url,
        headers={"Authorization": f"Bearer {access_token}"},
        method="GET",
    )
    return fetch_json(req)


def fetch_show(show_id: str, access_token: str, market: str) -> dict[str, Any]:
    # 1行で返す関数も普通に書ける。薄いラッパー関数として使いやすい。
    return api_get(f"/shows/{show_id}", access_token, {"market": market})


def fetch_all_episodes(show_id: str, access_token: str, market: str) -> list[dict[str, Any]]:
    # `episodes: list[dict[str, Any]] = []` は「空リストを作りつつ、この変数に何を入れる想定か」を示している。
    episodes: list[dict[str, Any]] = []
    limit = 50
    offset = 0

    while True:
        payload = api_get(
            f"/shows/{show_id}/episodes",
            access_token,
            {"market": market, "limit": limit, "offset": offset},
        )
        items = payload.get("items", [])
        episodes.extend(items)

        if not payload.get("next"):
            break
        offset += limit

    return episodes


def build_output(show: dict[str, Any], episodes: list[dict[str, Any]], market: str) -> dict[str, Any]:
    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "market": market,
        "show": {
            "id": show.get("id"),
            "name": show.get("name"),
            "publisher": show.get("publisher"),
            "description": show.get("description"),
            "html_description": show.get("html_description"),
            "total_episodes": show.get("total_episodes"),
            "external_urls": show.get("external_urls"),
        },
        # `for episode in episodes` を辞書の後ろに書くと、各要素をまとめて変換できる。
        "episodes": [
            {
                "id": episode.get("id"),
                "name": episode.get("name"),
                "description": episode.get("description"),
                "html_description": episode.get("html_description"),
                "release_date": episode.get("release_date"),
                "release_date_precision": episode.get("release_date_precision"),
                "duration_ms": episode.get("duration_ms"),
                "explicit": episode.get("explicit"),
                "is_externally_hosted": episode.get("is_externally_hosted"),
                "is_playable": episode.get("is_playable"),
                "language": episode.get("language"),
                "languages": episode.get("languages"),
                "external_urls": episode.get("external_urls"),
                "audio_preview_url": episode.get("audio_preview_url"),
            }
            for episode in episodes
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Spotify API から番組の全エピソードを取得して JSON に保存します。"
    )
    # 位置引数は `fetch_episodes.py <show_id>` のように名前なしで渡す。
    parser.add_argument("show_id", help="Spotify の番組 ID")
    parser.add_argument(
        "--market",
        default=os.getenv("SPOTIFY_MARKET", "JP"),
        help="Spotify API の market パラメータ。既定値は JP",
    )
    parser.add_argument(
        "--output",
        default="data/episodes.json",
        help="出力先 JSON パス。既定値は data/episodes.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        client_id = require_env("SPOTIFY_CLIENT_ID")
        client_secret = require_env("SPOTIFY_CLIENT_SECRET")
        access_token = request_access_token(client_id, client_secret)
        show = fetch_show(args.show_id, access_token, args.market)
        episodes = fetch_all_episodes(args.show_id, access_token, args.market)
        output = build_output(show, episodes, args.market)

        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            # `ensure_ascii=False` にすると、日本語が `\uXXXX` ではなくそのまま出力される。
            json.dumps(output, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"{len(episodes)} 件のエピソードを {output_path} に保存しました。")
    return 0


if __name__ == "__main__":
    # `SystemExit` を投げて終了コードを返すと、CLIスクリプトとして扱いやすい。
    raise SystemExit(main())
