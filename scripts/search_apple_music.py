import argparse
import csv
import json
import os
import re
import sys
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib import error, parse, request


API_BASE_URL = "https://api.music.apple.com/v1"
DEFAULT_LIMIT = 5
FEAT_PATTERN = re.compile(r"\s*(?:\(|（)?(?:feat\.?|ft\.?|with)\b.*$", re.IGNORECASE)
BRACKET_PATTERN = re.compile(r"\s*[\(\（].*?[\)\）]\s*")
SPACE_PATTERN = re.compile(r"\s+")


def require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"環境変数 {name} が設定されていません。")
    return value


def read_tracks(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            return list(csv.DictReader(csv_file))
    except FileNotFoundError as exc:
        raise RuntimeError(f"入力ファイルが見つかりません: {path}") from exc


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    text = text.replace("&", " and ")
    text = FEAT_PATTERN.sub("", text)
    text = BRACKET_PATTERN.sub(" ", text)
    text = re.sub(r"[^a-z0-9ぁ-んァ-ン一-龠ー\s]", " ", text)
    text = SPACE_PATTERN.sub(" ", text)
    return text.strip()


def simplify_title(text: str) -> str:
    simplified = FEAT_PATTERN.sub("", text)
    simplified = BRACKET_PATTERN.sub(" ", simplified)
    simplified = SPACE_PATTERN.sub(" ", simplified)
    return simplified.strip()


def build_query_variants(artist: str, title: str) -> list[str]:
    candidates = [
        f"{artist} {title}",
        f"{title} {artist}",
        f"{artist} {simplify_title(title)}",
        f"{simplify_title(title)} {artist}",
        title,
    ]
    queries: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        query = SPACE_PATTERN.sub(" ", candidate).strip()
        if query and query not in seen:
            seen.add(query)
            queries.append(query)
    return queries


def apple_music_get(
    path: str,
    developer_token: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    query = parse.urlencode(params)
    req = request.Request(
        f"{API_BASE_URL}{path}?{query}",
        headers={"Authorization": f"Bearer {developer_token}"},
        method="GET",
    )

    try:
        with request.urlopen(req) as res:
            return json.loads(res.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Apple Music API 呼び出しに失敗しました: HTTP {exc.code}\n{detail}"
        ) from exc
    except error.URLError as exc:
        raise RuntimeError(f"Apple Music API へ接続できませんでした: {exc.reason}") from exc


def search_catalog_songs(
    query: str,
    storefront: str,
    developer_token: str,
    limit: int,
) -> list[dict[str, Any]]:
    payload = apple_music_get(
        f"/catalog/{storefront}/search",
        developer_token,
        {"term": query, "types": "songs", "limit": limit},
    )
    return payload.get("results", {}).get("songs", {}).get("data", [])


def similarity_score(left: str, right: str) -> float:
    normalized_left = normalize_text(left)
    normalized_right = normalize_text(right)
    if not normalized_left or not normalized_right:
        return 0.0
    return SequenceMatcher(None, normalized_left, normalized_right).ratio()


def build_match_reason(
    source_artist: str,
    source_title: str,
    candidate_artist: str,
    candidate_title: str,
) -> str:
    reasons: list[str] = []
    if normalize_text(source_title) == normalize_text(candidate_title):
        reasons.append("title_exact")
    if normalize_text(source_artist) == normalize_text(candidate_artist):
        reasons.append("artist_exact")
    if not reasons:
        reasons.append("fuzzy_match")
    return ",".join(reasons)


def score_candidate(
    source_artist: str,
    source_title: str,
    candidate_artist: str,
    candidate_title: str,
) -> tuple[int, float, float, str]:
    title_score = similarity_score(source_title, candidate_title)
    artist_score = similarity_score(source_artist, candidate_artist)
    score = round((title_score * 0.7 + artist_score * 0.3) * 100)
    reason = build_match_reason(source_artist, source_title, candidate_artist, candidate_title)
    return score, round(title_score, 3), round(artist_score, 3), reason


def build_no_candidate_row(track: dict[str, str]) -> dict[str, str]:
    return {
        "episode_title": track["episode_title"],
        "published_at": track["published_at"],
        "track_no": track["track_no"],
        "source_artist": track["artist"],
        "source_title": track["title"],
        "source_raw_text": track["raw_text"],
        "query_text": "",
        "candidate_rank": "",
        "apple_music_id": "",
        "candidate_title": "",
        "candidate_artist": "",
        "candidate_album": "",
        "candidate_url": "",
        "match_score": "",
        "title_score": "",
        "artist_score": "",
        "match_reason": "no_candidate",
        "approved": "",
        "selected_apple_music_id": "",
        "notes": "",
    }


def search_candidates_for_track(
    track: dict[str, str],
    storefront: str,
    developer_token: str,
    limit: int,
) -> list[dict[str, str]]:
    source_artist = track["artist"]
    source_title = track["title"]
    seen_ids: set[str] = set()
    candidates: list[dict[str, str]] = []

    for query in build_query_variants(source_artist, source_title):
        for song in search_catalog_songs(query, storefront, developer_token, limit):
            song_id = song.get("id", "")
            if not song_id or song_id in seen_ids:
                continue

            seen_ids.add(song_id)
            attributes = song.get("attributes", {})
            candidate_title = attributes.get("name", "")
            candidate_artist = attributes.get("artistName", "")
            score, title_score, artist_score, reason = score_candidate(
                source_artist,
                source_title,
                candidate_artist,
                candidate_title,
            )
            candidates.append(
                {
                    "episode_title": track["episode_title"],
                    "published_at": track["published_at"],
                    "track_no": track["track_no"],
                    "source_artist": source_artist,
                    "source_title": source_title,
                    "source_raw_text": track["raw_text"],
                    "query_text": query,
                    "candidate_rank": "",
                    "apple_music_id": song_id,
                    "candidate_title": candidate_title,
                    "candidate_artist": candidate_artist,
                    "candidate_album": attributes.get("albumName", ""),
                    "candidate_url": attributes.get("url", ""),
                    "match_score": str(score),
                    "title_score": f"{title_score:.3f}",
                    "artist_score": f"{artist_score:.3f}",
                    "match_reason": reason,
                    "approved": "",
                    "selected_apple_music_id": "",
                    "notes": "",
                }
            )

    candidates.sort(
        key=lambda row: (
            -int(row["match_score"]),
            -float(row["title_score"]),
            -float(row["artist_score"]),
            row["candidate_title"],
        )
    )

    for index, row in enumerate(candidates[:limit], start=1):
        row["candidate_rank"] = str(index)

    if not candidates:
        return [build_no_candidate_row(track)]

    return candidates[:limit]


def write_candidates(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "episode_title",
        "published_at",
        "track_no",
        "source_artist",
        "source_title",
        "source_raw_text",
        "query_text",
        "candidate_rank",
        "apple_music_id",
        "candidate_title",
        "candidate_artist",
        "candidate_album",
        "candidate_url",
        "match_score",
        "title_score",
        "artist_score",
        "match_reason",
        "approved",
        "selected_apple_music_id",
        "notes",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="tracks.csv をもとに Apple Music の候補 CSV を生成します。"
    )
    parser.add_argument(
        "--input",
        default="data/tracks.csv",
        help="入力 CSV パス。既定値は data/tracks.csv",
    )
    parser.add_argument(
        "--output",
        default="data/apple_music_candidates.csv",
        help="出力 CSV パス。既定値は data/apple_music_candidates.csv",
    )
    parser.add_argument(
        "--storefront",
        default=os.getenv("APPLE_MUSIC_STOREFRONT", "jp"),
        help="Apple Music storefront。既定値は jp",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help="1曲あたりの候補出力件数。既定値は 5",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        developer_token = require_env("APPLE_MUSIC_DEVELOPER_TOKEN")
        tracks = read_tracks(Path(args.input))
        searchable_tracks = [track for track in tracks if track.get("extraction_status") == "ok"]

        rows: list[dict[str, str]] = []
        for track in searchable_tracks:
            rows.extend(
                search_candidates_for_track(
                    track=track,
                    storefront=args.storefront,
                    developer_token=developer_token,
                    limit=args.limit,
                )
            )

        write_candidates(Path(args.output), rows)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"{len(rows)} 件の候補行を {args.output} に保存しました。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
