"""
Bedrock AgentCore Runtime用エントリポイント。

このファイルはAWS Bedrock AgentCore Runtimeにデプロイする際に使用します。
ローカル開発では agent.py を直接実行してください。
"""

import logging
import os

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from dotenv import load_dotenv
from mcp import StdioServerParameters, stdio_client
from strands import Agent
from strands.tools.mcp import MCPClient
from strands_tools.tavily import tavily_search

from tools import (
    add_place,
    find_nearby_places,
    geocode,
    get_current_datetime,
    get_distance,
    get_google_maps_route_url,
)

# 環境変数を読み込み
load_dotenv()

# ロギング設定
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def validate_environment() -> dict[str, str]:
    """
    必須環境変数を検証します。

    Returns:
        検証済みの環境変数辞書

    Raises:
        ValueError: 必須環境変数が設定されていない場合
    """
    required_env_vars = {
        "NOTION_TOKEN": os.environ.get("NOTION_TOKEN"),
        "NOTION_DATABASE_ID": os.environ.get("NOTION_DATABASE_ID"),
        "NOTION_DATA_SOURCE_ID": os.environ.get("NOTION_DATA_SOURCE_ID"),
        "TAVILY_API_KEY": os.environ.get("TAVILY_API_KEY"),
    }

    missing_vars = [key for key, value in required_env_vars.items() if not value]
    if missing_vars:
        error_msg = f"Required environment variables are missing: {', '.join(missing_vars)}"
        logger.error(error_msg)
        raise ValueError(error_msg)

    return required_env_vars


# 環境変数を検証して取得
env_vars = validate_environment()
NOTION_TOKEN = env_vars["NOTION_TOKEN"]
NOTION_DATABASE_ID = env_vars["NOTION_DATABASE_ID"]
NOTION_DATA_SOURCE_ID = env_vars["NOTION_DATA_SOURCE_ID"]

# BedrockAgentCoreApp の初期化
app = BedrockAgentCoreApp()


# システムプロンプト
SYSTEM_PROMPT = f"""あなたは「行きたいところリスト」を管理するアシスタントです。
ユーザーからのメッセージに対して、親切で簡潔に日本語で応答してください。

## あなたができること

1. **行きたいところリストの確認**: Notionデータベースから現在の行きたいところリストを取得して表示します。
   - 「行きたいところリストを見せて」「リスト一覧」などと言われたら表示します。
   - データベースをクエリするには `API-query-data-source` を使い、`data_source_id` に `{NOTION_DATA_SOURCE_ID}` を指定してください。
   - **重要**: 削除済みアイテムを除外するため、filterで `{{"property": "論理削除", "select": {{"does_not_equal": "削除済み"}}}}` を指定してください。
   - データベース情報を取得するには `API-retrieve-a-database` を使い、`database_id` に `{NOTION_DATABASE_ID}` を指定してください。

2. **新しい場所の追加**: ユーザーが「〇〇を追加して」「行きたいところリストに△△を入れて」と言った場合、
   `add_place` ツールを使用してNotionデータベースに新しいアイテムを作成します。
   - 引数:
     - name: 場所の名前（必須）
     - category: 「旅行」「飲食店」「買い物」「その他」から選択（デフォルト: その他）
     - priority: 「高」「中」「低」から選択（デフォルト: 中）
     - memo: メモ（任意）
     - address: 住所（任意、距離検索に使用）
   - 必要に応じてユーザーにカテゴリや優先度を確認してください
   - **住所は必ず埋めてください**。会話の内容から住所を特定できる場合はそのまま使用し、特定できない場合はユーザーに質問してください。ユーザーが答えない・空を指定した場合のみ空のままにしてください

3. **場所の削除（論理削除）**: ユーザーが「〇〇を削除して」「△△を消して」と言った場合、
   該当するアイテムを論理削除します。
   - まず `API-query-data-source` で名前から該当ページを検索してください。
   - 検索時は `data_source_id`: `{NOTION_DATA_SOURCE_ID}` を指定し、filterで名前に検索語を含むものに限定してください。
   - ページIDを取得したら、`API-update-a-page` を使用して「論理削除」プロパティ（select型）を「削除済み」に更新してください。
     更新時のproperties: `{{"論理削除": {{"select": {{"name": "削除済み"}}}}}}`
   - 該当する場所が見つからない場合は、その旨を伝えてください。
   - 複数の候補がある場合は、ユーザーに確認してください。

4. **場所に関する情報検索**: 「〇〇について調べて」「△△の情報を教えて」と言われた場合、
   Web検索を行って情報を提供します。
   - 検索結果を要約して、わかりやすく伝えてください。

5. **近くの場所検索**: 「〇〇から近い場所は？」「新宿駅周辺でリストにあるものは？」と言われた場合、
   `find_nearby_places` ツールを使用して、指定地点から近い順に場所を検索します。
   - 引数:
     - reference_location: 基準となる場所（住所または場所名）
     - max_distance_km: 検索する最大距離（km）。デフォルトは10km
   - リスト内の各場所の「住所」プロパティを元に距離を計算します

6. **距離の計算**: 「〇〇から△△までの距離は？」と言われた場合、
   `get_distance` ツールを使用して2点間の直線距離を計算します。

7. **座標の取得**: 「〇〇の座標は？」と言われた場合、
   `geocode` ツールを使用して住所や場所名から座標を取得します。

8. **現在日時の取得**: 「今何時？」「今日の日付は？」と言われた場合、
   `get_current_datetime` ツールを使用して現在の日時を取得します。

9. **Googleマップで経路を表示**: 「〇〇から△△への行き方は？」「〇〇への経路を教えて」と言われた場合、
   `get_google_maps_route_url` ツールを使用してGoogleマップの経路URLを生成します。
   - 引数:
     - origin: 出発地（場所名または住所）
     - destination: 目的地（場所名または住所）
     - waypoints: 経由地（「|」区切りで複数指定可能、省略可）
     - travel_mode: 移動手段（「車」「電車」「徒歩」「自転車」、省略可）
   - 距離計算の結果と組み合わせて、経路URLも一緒に提供すると便利です

## 位置情報の活用

ユーザーがLINEで位置情報を共有すると、「ユーザーが現在地を共有しました。」というメッセージとともに場所名・住所・座標が送られます。
この情報を使って、近くの場所検索（`find_nearby_places`）、経路URL生成（`get_google_maps_route_url`）、距離計算（`get_distance`）などを積極的に提案してください。

## 応答のガイドライン

- 簡潔で親しみやすい口調で応答してください。
- リストを表示する際は、見やすく整形してください。
- エラーが発生した場合は、何が問題かを説明してください。
- 不明な点があれば、確認してから行動してください。
"""


def create_notion_mcp_client() -> MCPClient:
    """Notion MCP クライアントを作成します。"""
    # コンテナ環境ではグローバルインストールされたMCPサーバーを使用
    # ローカル環境ではnpxを使用
    import shutil

    if shutil.which("notion-mcp-server"):
        # グローバルインストールされている場合
        command = "notion-mcp-server"
        args = []
    else:
        # npxを使用（ローカル開発用）
        command = "npx"
        args = ["-y", "@notionhq/notion-mcp-server"]

    return MCPClient(
        lambda: stdio_client(
            StdioServerParameters(
                command=command,
                args=args,
                env={
                    **os.environ,
                    "NOTION_TOKEN": NOTION_TOKEN,
                },
            )
        ),
        startup_timeout=30,
    )


# エージェントのシングルトンインスタンス
_agent = None


def get_agent() -> Agent:
    """
    エージェントのシングルトンインスタンスを取得します。
    MCPクライアントの再利用によりパフォーマンスを向上させます。
    """
    global _agent
    if _agent is None:
        notion_mcp = create_notion_mcp_client()
        _agent = Agent(
            system_prompt=SYSTEM_PROMPT,
            tools=[
                notion_mcp,
                add_place,
                tavily_search,
                geocode,
                get_distance,
                find_nearby_places,
                get_current_datetime,
                get_google_maps_route_url,
            ],
            model="jp.anthropic.claude-haiku-4-5-20251001-v1:0",
        )
    return _agent


@app.entrypoint
def invoke(payload: dict, context=None) -> dict:
    """
    AgentCore Runtime からの呼び出しを処理します。

    Args:
        payload: リクエストペイロード（"prompt" キーにユーザーメッセージ）
        context: AgentCore コンテキスト（オプション）

    Returns:
        レスポンス辞書
    """
    try:
        user_message = payload.get("prompt", "")
        if not user_message:
            return {"error": "No prompt provided"}

        logger.info(f"Processing message: {user_message}")

        agent = get_agent()
        result = agent(user_message)

        return {"result": str(result)}

    except Exception as e:
        logger.error(f"Agent invocation failed: {e}", exc_info=True)
        return {
            "error": "処理中にエラーが発生しました。",
            "details": str(e),
        }


if __name__ == "__main__":
    app.run()
