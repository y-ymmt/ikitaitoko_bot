"""
カスタムツール定義。

このファイルには行きたいところリストBotで使用するカスタムツールを定義します。
- add_place: Notionに新しい場所を追加
- geocode: 住所/場所名から座標を取得
- calculate_distance: 2点間の距離を計算
- find_nearby_places: 指定地点から近い場所を検索
- get_google_maps_route_url: Googleマップの経路URLを生成
"""

import logging
import math
import os
from datetime import datetime
from typing import Optional
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests

from strands import tool

logger = logging.getLogger(__name__)

# 環境変数
NOTION_TOKEN = os.environ.get("NOTION_TOKEN", "")
NOTION_DATABASE_ID = os.environ.get("NOTION_DATABASE_ID", "")


# =============================================================================
# ジオコーディング関数（内部用）
# =============================================================================


def geocode_address(query: str) -> Optional[tuple[float, float]]:
    """
    国土地理院APIで住所/場所名から座標を取得します。

    Args:
        query: 住所または場所名

    Returns:
        (緯度, 経度) のタプル。見つからない場合はNone
    """
    try:
        url = "https://msearch.gsi.go.jp/address-search/AddressSearch"
        response = requests.get(url, params={"q": query}, timeout=10)
        response.raise_for_status()
        results = response.json()

        if results and len(results) > 0:
            # [経度, 緯度] の順で返ってくるので注意
            lon, lat = results[0]["geometry"]["coordinates"]
            logger.info(f"GSI geocode success: {query} -> ({lat}, {lon})")
            return (lat, lon)

        logger.info(f"GSI geocode: no results for {query}")
        return None

    except Exception as e:
        logger.warning(f"GSI geocode failed for {query}: {e}")
        return None


def calculate_distance_km(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """
    2点間の距離をHaversine公式で計算します。

    Args:
        lat1: 地点1の緯度
        lon1: 地点1の経度
        lat2: 地点2の緯度
        lon2: 地点2の経度

    Returns:
        距離（km）
    """
    # 地球の半径（km）
    R = 6371.0

    # 緯度経度をラジアンに変換
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    # Haversine公式
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


# =============================================================================
# Strands ツール定義
# =============================================================================


# 日本のタイムゾーン
JST = ZoneInfo("Asia/Tokyo")

# 日本語の曜日名
_WEEKDAY_NAMES = ["月", "火", "水", "木", "金", "土", "日"]


@tool
def get_current_datetime() -> str:
    """
    現在の日時を日本標準時（JST）で取得します。

    Returns:
        現在の日時情報（日本語フォーマット、曜日・週番号付き）
    """
    now = datetime.now(JST)
    weekday = _WEEKDAY_NAMES[now.weekday()]
    iso_week = now.isocalendar()[1]

    return (
        f"現在の日時: {now.year}年{now.month}月{now.day}日（{weekday}）"
        f"{now.hour:02d}:{now.minute:02d} JST"
        f"\n第{iso_week}週"
    )


@tool
def add_place(
    name: str,
    category: str = "その他",
    priority: str = "中",
    memo: str = "",
    address: str = "",
) -> str:
    """
    行きたいところリストに新しい場所を追加します。

    Args:
        name: 追加する場所の名前（必須）
        category: カテゴリ。「旅行」「飲食店」「買い物」「その他」のいずれか。デフォルトは「その他」
        priority: 優先度。「高」「中」「低」のいずれか。デフォルトは「中」
        memo: メモ（任意）
        address: 住所（任意）。距離検索に使用されます

    Returns:
        作成結果のメッセージ
    """
    valid_categories = ["旅行", "飲食店", "買い物", "その他"]
    valid_priorities = ["高", "中", "低"]

    if category not in valid_categories:
        category = "その他"
    if priority not in valid_priorities:
        priority = "中"

    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }

    properties = {
        "名前": {"title": [{"type": "text", "text": {"content": name}}]},
        "カテゴリ": {"select": {"name": category}},
        "優先度": {"select": {"name": priority}},
        "行った": {"checkbox": False},
    }

    if memo:
        properties["メモ"] = {"rich_text": [{"type": "text", "text": {"content": memo}}]}

    if address:
        properties["住所"] = {"rich_text": [{"type": "text", "text": {"content": address}}]}

    payload = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": properties,
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        result_msg = f"「{name}」を行きたいところリストに追加しました！\nカテゴリ: {category}\n優先度: {priority}"
        if address:
            result_msg += f"\n住所: {address}"
        return result_msg
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to add place: {e}")
        return f"場所の追加に失敗しました: {str(e)}"


@tool
def geocode(query: str) -> str:
    """
    住所や場所名から座標（緯度・経度）を取得します。

    Args:
        query: 住所または場所名（例: "東京都渋谷区"、"新宿駅"、"東京タワー"）

    Returns:
        座標情報を含むメッセージ
    """
    result = geocode_address(query)

    if result:
        lat, lon = result
        return f"「{query}」の座標:\n緯度: {lat}\n経度: {lon}"
    else:
        return f"「{query}」の座標を取得できませんでした。より具体的な住所や場所名を指定してください。"


@tool
def get_distance(origin: str, destination: str) -> str:
    """
    2つの場所間の直線距離を計算します。

    Args:
        origin: 出発地点（住所または場所名、例: "新宿駅"）
        destination: 目的地（住所または場所名、例: "東京タワー"）

    Returns:
        距離情報を含むメッセージ
    """
    origin_coords = geocode_address(origin)
    if not origin_coords:
        return f"出発地点「{origin}」の座標を取得できませんでした。"

    dest_coords = geocode_address(destination)
    if not dest_coords:
        return f"目的地「{destination}」の座標を取得できませんでした。"

    distance = calculate_distance_km(
        origin_coords[0], origin_coords[1],
        dest_coords[0], dest_coords[1]
    )

    return f"「{origin}」から「{destination}」までの直線距離: 約 {distance:.1f} km"


@tool
def find_nearby_places(
    reference_location: str,
    max_distance_km: float = 10.0,
) -> str:
    """
    指定した場所から近い順に、行きたいところリストの場所を検索します。
    Notionデータベースの「住所」プロパティを元に距離を計算します。

    Args:
        reference_location: 基準となる場所（住所または場所名、例: "新宿駅"、"東京都渋谷区"）
        max_distance_km: 検索する最大距離（km）。デフォルトは10km

    Returns:
        近い場所のリストを含むメッセージ
    """
    # 基準地点の座標を取得
    ref_coords = geocode_address(reference_location)
    if not ref_coords:
        return f"基準地点「{reference_location}」の座標を取得できませんでした。より具体的な住所や場所名を指定してください。"

    ref_lat, ref_lon = ref_coords

    # Notionデータベースから全件取得
    url = f"https://api.notion.com/v1/databases/{NOTION_DATABASE_ID}/query"
    headers = {
        "Authorization": f"Bearer {NOTION_TOKEN}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28",
    }

    # 論理削除されていないアイテムのみ取得
    payload = {
        "filter": {
            "or": [
                {
                    "property": "論理削除",
                    "select": {"does_not_equal": "削除済み"}
                },
                {
                    "property": "論理削除",
                    "select": {"is_empty": True}
                }
            ]
        }
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to query Notion: {e}")
        return f"Notionデータベースの取得に失敗しました: {str(e)}"

    results = data.get("results", [])
    if not results:
        return "行きたいところリストに登録されている場所がありません。"

    # 各場所の距離を計算
    places_with_distance = []
    places_without_address = []

    for item in results:
        props = item.get("properties", {})

        # 名前を取得
        name_prop = props.get("名前", {})
        title_list = name_prop.get("title", [])
        name = title_list[0].get("plain_text", "（名前なし）") if title_list else "（名前なし）"

        # 住所を取得
        address_prop = props.get("住所", {})
        rich_text_list = address_prop.get("rich_text", [])
        address = rich_text_list[0].get("plain_text", "") if rich_text_list else ""

        # カテゴリを取得
        category_prop = props.get("カテゴリ", {})
        category_select = category_prop.get("select")
        category = category_select.get("name", "") if category_select else ""

        if not address:
            places_without_address.append({"name": name, "category": category})
            continue

        # 座標を取得
        place_coords = geocode_address(address)
        if not place_coords:
            places_without_address.append({"name": name, "category": category, "address": address})
            continue

        # 距離を計算
        distance = calculate_distance_km(ref_lat, ref_lon, place_coords[0], place_coords[1])

        if distance <= max_distance_km:
            places_with_distance.append({
                "name": name,
                "category": category,
                "address": address,
                "distance": distance,
            })

    # 距離でソート
    places_with_distance.sort(key=lambda x: x["distance"])

    # 結果を整形
    result_lines = [f"「{reference_location}」から {max_distance_km}km 以内の場所:\n"]

    if places_with_distance:
        for i, place in enumerate(places_with_distance, 1):
            line = f"{i}. {place['name']}"
            if place["category"]:
                line += f" [{place['category']}]"
            line += f"\n   距離: {place['distance']:.1f}km"
            line += f"\n   住所: {place['address']}"
            result_lines.append(line)
    else:
        result_lines.append(f"該当する場所はありませんでした（{max_distance_km}km以内）。")

    if places_without_address:
        result_lines.append(f"\n※ 住所が未登録で検索できなかった場所が {len(places_without_address)} 件あります:")
        for place in places_without_address[:5]:  # 最大5件まで表示
            result_lines.append(f"  - {place['name']}")
        if len(places_without_address) > 5:
            result_lines.append(f"  ... 他 {len(places_without_address) - 5} 件")

    return "\n".join(result_lines)


# Googleマップの移動手段マッピング
_TRAVEL_MODE_MAP = {
    "車": "driving",
    "driving": "driving",
    "電車": "transit",
    "transit": "transit",
    "徒歩": "walking",
    "walking": "walking",
    "自転車": "bicycling",
    "bicycling": "bicycling",
}


@tool
def get_google_maps_route_url(
    origin: str,
    destination: str,
    waypoints: str = "",
    travel_mode: str = "",
) -> str:
    """
    Googleマップで経路を表示するURLを生成します。

    Args:
        origin: 出発地（場所名または住所、例: "新宿駅"、"東京都渋谷区道玄坂1-1"）
        destination: 目的地（場所名または住所、例: "東京タワー"）
        waypoints: 経由地。複数ある場合は「|」で区切る（例: "渋谷駅|品川駅"）。省略可
        travel_mode: 移動手段。「車」「電車」「徒歩」「自転車」のいずれか。省略するとGoogleマップのデフォルト

    Returns:
        Googleマップの経路URL
    """
    params = [
        f"origin={quote(origin)}",
        f"destination={quote(destination)}",
    ]

    # 経由地: 各地点を個別にエンコードし、パイプで結合（パイプ自体はエンコードしない）
    waypoint_list = [wp.strip() for wp in waypoints.split("|") if wp.strip()] if waypoints else []
    if waypoint_list:
        encoded_waypoints = "|".join(quote(wp) for wp in waypoint_list)
        params.append(f"waypoints={encoded_waypoints}")

    # 移動手段
    resolved_mode = ""
    if travel_mode:
        resolved_mode = _TRAVEL_MODE_MAP.get(travel_mode.lower(), "")
        if resolved_mode:
            params.append(f"travelmode={resolved_mode}")

    url = "https://www.google.com/maps/dir/?api=1&" + "&".join(params)

    result = f"Googleマップで経路を確認:\n{url}"
    result += f"\n\n出発地: {origin}\n目的地: {destination}"
    if waypoint_list:
        result += f"\n経由地: {' → '.join(waypoint_list)}"
    if travel_mode:
        if resolved_mode:
            result += f"\n移動手段: {travel_mode}"
        else:
            result += f"\n※ 移動手段「{travel_mode}」は無効です。Googleマップのデフォルトが使用されます。"

    return result
