import argparse
import json
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, request


ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"


def fetch_xml(url: str) -> ET.Element:
    # `-> ET.Element` のような型ヒントは、XMLのルート要素を返す意図を示している。
    req = request.Request(
        url,
        headers={"User-Agent": "podcast-playlist-builder/1.0"},
        method="GET",
    )

    try:
        # `with` を使うと、レスポンスを使い終わった後の後始末を Python に任せられる。
        with request.urlopen(req) as res:
            xml_text = res.read().decode("utf-8")
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"RSS の取得に失敗しました: HTTP {exc.code}\n{detail}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"RSS へ接続できませんでした: {exc.reason}") from exc

    try:
        return ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise RuntimeError(f"RSS XML を解析できませんでした: {exc}") from exc


def find_text(element: ET.Element | None, path: str, default: str = "") -> str:
    # `element is None` のような判定は、値が存在しないケースを先に弾く Python の基本形。
    if element is None:
        return default

    found = element.find(path)
    if found is None or found.text is None:
        return default
    return found.text.strip()


def parse_episode(item: ET.Element) -> dict[str, Any]:
    enclosure = item.find("enclosure")

    # `dict[str, Any]` は「キーが文字列の辞書」を返す想定を表している。
    return {
        "title": find_text(item, "title"),
        "description": find_text(item, "description"),
        "content_encoded": find_text(item, f"{{{CONTENT_NS}}}encoded"),
        "summary": find_text(item, f"{{{ITUNES_NS}}}summary"),
        "published_at": find_text(item, "pubDate"),
        "guid": find_text(item, "guid"),
        "link": find_text(item, "link"),
        "episode_url": enclosure.get("url", "") if enclosure is not None else "",
        "episode_type": find_text(item, f"{{{ITUNES_NS}}}episodeType"),
        "duration": find_text(item, f"{{{ITUNES_NS}}}duration"),
    }


def parse_feed(root: ET.Element, rss_url: str) -> dict[str, Any]:
    channel = root.find("channel")
    if channel is None:
        raise RuntimeError("RSS に channel 要素が見つかりませんでした。")

    items = channel.findall("item")
    episodes = [parse_episode(item) for item in items]

    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": {"type": "rss", "url": rss_url},
        "podcast": {
            "title": find_text(channel, "title"),
            "description": find_text(channel, "description"),
            "language": find_text(channel, "language"),
            "link": find_text(channel, "link"),
            "author": find_text(channel, f"{{{ITUNES_NS}}}author"),
            "summary": find_text(channel, f"{{{ITUNES_NS}}}summary"),
        },
        # リスト内包表記は「各 item を同じルールで変換した新しい list を作る」書き方。
        "episodes": episodes,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Podcast RSS から全エピソードを取得して JSON に保存します。"
    )
    # 位置引数は `python ... <rss_url>` のように、名前を付けず順番で渡す。
    parser.add_argument("rss_url", help="Podcast RSS の URL")
    parser.add_argument(
        "--output",
        default="data/episodes.json",
        help="出力先 JSON パス。既定値は data/episodes.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        root = fetch_xml(args.rss_url)
        output = parse_feed(root, args.rss_url)

        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            # `ensure_ascii=False` で日本語をそのまま保存し、`indent=2` で見やすく整形する。
            json.dumps(output, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"{len(output['episodes'])} 件のエピソードを {output_path} に保存しました。")
    return 0


if __name__ == "__main__":
    # `SystemExit(main())` にすると、return した整数を終了コードとして返せる。
    raise SystemExit(main())
