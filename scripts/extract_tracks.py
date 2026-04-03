import argparse
import csv
import json
import re
import sys
from html import unescape
from pathlib import Path
from typing import Any


TRACK_SECTION_MARKERS = [
    "本編で紹介した曲はこちら",
]

TRACK_SECTION_END_MARKERS = [
    "田中渓エックスアカウント",
    "ハッシュタグ",
    "番組メールアドレス",
    "番組プレイリスト",
    "各種リンク先はこちら",
]

MAIN_TRACK_RE = re.compile(r"^\s*M\s*([0-9０-９]+)\s*[.．]?\s*(.+?)\s*$")
SUB_TRACK_RE = re.compile(r"^\s*([①②③④⑤⑥⑦⑧⑨⑩])\s*(.+?)\s*$")
TAG_RE = re.compile(r"<[^>]+>")

CIRCLED_NUM_MAP = {
    "①": 1,
    "②": 2,
    "③": 3,
    "④": 4,
    "⑤": 5,
    "⑥": 6,
    "⑦": 7,
    "⑧": 8,
    "⑨": 9,
    "⑩": 10,
}


def should_skip_raw_text(raw_text: str) -> bool:
    normalized = raw_text.strip()
    if normalized == "K’ｓ-Mix DJ Kei Side 1":
        return True
    if normalized == "絵のない絵本 ～第12夜～":
        return True
    return False


def load_episodes(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"入力ファイルが見つかりません: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"JSON を読み込めませんでした: {path}\n{exc}") from exc


def normalize_text(text: str) -> str:
    text = unescape(text)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.IGNORECASE)
    text = TAG_RE.sub("", text)
    text = text.replace("\u00a0", " ")
    text = text.replace("\u3000", " ")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def choose_source_text(episode: dict[str, Any]) -> tuple[str, str]:
    for field in ("content_encoded", "description", "summary"):
        raw = episode.get(field) or ""
        normalized = normalize_text(raw)
        if normalized:
            return field, normalized
    return "", ""


def extract_track_section(text: str) -> str:
    start_index = -1
    marker_length = 0
    for marker in TRACK_SECTION_MARKERS:
        index = text.find(marker)
        if index != -1:
            start_index = index
            marker_length = len(marker)
            break

    if start_index == -1:
        return ""

    section = text[start_index + marker_length :]
    end_indexes = [section.find(marker) for marker in TRACK_SECTION_END_MARKERS if section.find(marker) != -1]
    if end_indexes:
        section = section[: min(end_indexes)]

    return section.strip()


def prepare_section_lines(section: str) -> list[str]:
    # M1 のような主番号の前に改行を補って、1曲ずつ扱いやすくする。
    section = re.sub(r"\s+(?=M\s*[0-9０-９]+\s*[.．]?)", "\n", section)
    # ① のような枝番も改行へ分離する。
    section = re.sub(r"\s+(?=[①②③④⑤⑥⑦⑧⑨⑩])", "\n", section)
    lines = [line.strip() for line in section.splitlines()]
    return [line for line in lines if line]


def normalize_track_no(text: str) -> str:
    return text.translate(str.maketrans("０１２３４５６７８９", "0123456789"))


def split_artist_and_title(raw_text: str) -> tuple[str, str, str]:
    cleaned = raw_text.strip(" -")

    if " / " in cleaned:
        left, right = cleaned.split(" / ", 1)
        return left.strip(), right.strip(), "ok"

    slash_index = cleaned.find("/")
    if slash_index != -1:
        left = cleaned[:slash_index]
        right = cleaned[slash_index + 1 :]
        return left.strip(), right.strip(), "ok"

    if " _ " in cleaned:
        left, right = cleaned.split(" _ ", 1)
        return left.strip(" _"), right.strip(" _"), "ok"

    if "_" in cleaned:
        left, right = cleaned.split("_", 1)
        return left.strip(" _"), right.strip(" _"), "ok"

    if " - " in cleaned:
        left, right = cleaned.split(" - ", 1)
        return left.strip(), right.strip(), "ok"

    hyphen_match = re.match(r"^(.+?)-\s+(.+)$", cleaned)
    if hyphen_match:
        return hyphen_match.group(1).strip(), hyphen_match.group(2).strip(), "ok"

    return "", "", "needs_review"


def build_track_row(
    episode: dict[str, Any],
    source_field: str,
    track_no: str,
    raw_text: str,
) -> dict[str, str] | None:
    if should_skip_raw_text(raw_text):
        return None

    artist, title, status = split_artist_and_title(raw_text)
    return {
        "episode_title": episode.get("title", ""),
        "published_at": episode.get("published_at", ""),
        "track_no": track_no,
        "artist": artist,
        "title": title,
        "raw_text": raw_text,
        "source_field": source_field,
        "extraction_status": status,
    }


def extract_tracks_from_episode(episode: dict[str, Any]) -> list[dict[str, str]]:
    source_field, source_text = choose_source_text(episode)
    if not source_text:
        return []

    section = extract_track_section(source_text)
    if not section:
        return []

    lines = prepare_section_lines(section)
    rows: list[dict[str, str]] = []
    current_main_track_no = ""

    for line in lines:
        main_match = MAIN_TRACK_RE.match(line)
        if main_match:
            current_main_track_no = normalize_track_no(main_match.group(1))
            row = build_track_row(
                episode=episode,
                source_field=source_field,
                track_no=current_main_track_no,
                raw_text=main_match.group(2).strip(),
            )
            if row:
                rows.append(row)
            continue

        sub_match = SUB_TRACK_RE.match(line)
        if sub_match and current_main_track_no:
            sub_no = CIRCLED_NUM_MAP[sub_match.group(1)]
            row = build_track_row(
                episode=episode,
                source_field=source_field,
                track_no=f"{current_main_track_no}-{sub_no}",
                raw_text=sub_match.group(2).strip(),
            )
            if row:
                rows.append(row)
            continue

    return rows


def extract_tracks(episodes_data: dict[str, Any]) -> list[dict[str, str]]:
    episodes = episodes_data.get("episodes", [])
    rows: list[dict[str, str]] = []
    for episode in episodes:
        rows.extend(extract_tracks_from_episode(episode))
    return rows


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "episode_title",
        "published_at",
        "track_no",
        "artist",
        "title",
        "raw_text",
        "source_field",
        "extraction_status",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="episodes.json から曲候補を抽出して CSV に保存します。"
    )
    parser.add_argument(
        "--input",
        default="data/episodes.json",
        help="入力 JSON パス。既定値は data/episodes.json",
    )
    parser.add_argument(
        "--output",
        default="data/tracks.csv",
        help="出力 CSV パス。既定値は data/tracks.csv",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        episodes_data = load_episodes(Path(args.input))
        rows = extract_tracks(episodes_data)
        write_csv(Path(args.output), rows)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"{len(rows)} 件の曲候補を {args.output} に保存しました。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
