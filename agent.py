"""
LINE Bot AI Agent with Notion MCP integration and AgentCore Memory.

このエージェントはLINE Botとして動作し、以下の機能を提供します：
1. LINEグループでメンションされた際に会話に応答
2. Notion「行きたいところリスト」DBの参照・新規追加
3. Tavily Searchを使った場所に関する情報検索
4. AgentCore Memoryを使った会話履歴の保持
"""

import logging
import os
from typing import Optional

from dotenv import load_dotenv
from flask import Flask, abort, request
from linebot.v3.exceptions import InvalidSignatureError
from mcp import StdioServerParameters, stdio_client
from strands import Agent
from strands.tools.mcp import MCPClient
from strands_tools.tavily import tavily_search

from line_handler import LineHandler
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
        "LINE_CHANNEL_ACCESS_TOKEN": os.environ.get("LINE_CHANNEL_ACCESS_TOKEN"),
        "LINE_CHANNEL_SECRET": os.environ.get("LINE_CHANNEL_SECRET"),
        "NOTION_TOKEN": os.environ.get("NOTION_TOKEN"),
        "NOTION_DATABASE_ID": os.environ.get("NOTION_DATABASE_ID"),
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
LINE_CHANNEL_ACCESS_TOKEN = env_vars["LINE_CHANNEL_ACCESS_TOKEN"]
LINE_CHANNEL_SECRET = env_vars["LINE_CHANNEL_SECRET"]
NOTION_TOKEN = env_vars["NOTION_TOKEN"]
NOTION_DATABASE_ID = env_vars["NOTION_DATABASE_ID"]

# AgentCore Memory設定（オプション）
AGENTCORE_MEMORY_ID = os.environ.get("AGENTCORE_MEMORY_ID")
AGENTCORE_REGION = os.environ.get("AGENTCORE_REGION", "us-east-1")

# Flask アプリケーション
app = Flask(__name__)

# LINE ハンドラーの初期化
line_handler = LineHandler(LINE_CHANNEL_ACCESS_TOKEN, LINE_CHANNEL_SECRET)

# Notion Data Source ID（データベースクエリに使用）
# database_idからAPI-retrieve-a-databaseで取得したdata_sources[0].id
NOTION_DATA_SOURCE_ID = os.environ.get("NOTION_DATA_SOURCE_ID", "")


# システムプロンプト
SYSTEM_PROMPT = f"""あなたは「行きたいところリスト」を管理するアシスタントです。
ユーザーからのLINEメッセージに対して、親切で簡潔に日本語で応答してください。

## あなたができること

1. **行きたいところリストの確認**: Notionデータベースから現在の行きたいところリストを取得して表示します。
   - 「行きたいところリストを見せて」「リスト一覧」などと言われたら表示します。
   - データベースをクエリするには `API-query-data-source` を使い、`data_source_id` に `{NOTION_DATA_SOURCE_ID}` を指定してください。
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

3. **場所に関する情報検索**: 「〇〇について調べて」「△△の情報を教えて」と言われた場合、
   Web検索を行って情報を提供します。
   - 検索結果を要約して、わかりやすく伝えてください。

4. **近くの場所検索**: 「〇〇から近い場所は？」「新宿駅周辺でリストにあるものは？」と言われた場合、
   `find_nearby_places` ツールを使用して、指定地点から近い順に場所を検索します。
   - 引数:
     - reference_location: 基準となる場所（住所または場所名）
     - max_distance_km: 検索する最大距離（km）。デフォルトは10km
   - リスト内の各場所の「住所」プロパティを元に距離を計算します

5. **距離の計算**: 「〇〇から△△までの距離は？」と言われた場合、
   `get_distance` ツールを使用して2点間の直線距離を計算します。

6. **座標の取得**: 「〇〇の座標は？」と言われた場合、
   `geocode` ツールを使用して住所や場所名から座標を取得します。

7. **現在日時の取得**: 「今何時？」「今日の日付は？」と言われた場合、
   `get_current_datetime` ツールを使用して現在の日時を取得します。

8. **Googleマップで経路を表示**: 「〇〇から△△への行き方は？」「〇〇への経路を教えて」と言われた場合、
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
- 過去の会話内容を覚えている場合は、それを活用して応答してください。
"""


def create_notion_mcp_client() -> MCPClient:
    """Notion MCP クライアントを作成します。"""
    return MCPClient(
        lambda: stdio_client(
            StdioServerParameters(
                command="npx",
                args=["-y", "@notionhq/notion-mcp-server"],
                env={
                    **os.environ,
                    "NOTION_TOKEN": NOTION_TOKEN,
                },
            )
        ),
        startup_timeout=30,
    )


# MCPクライアントはシングルトンとして保持（起動コストが高いため）
_notion_mcp_client = None


def get_notion_mcp_client() -> MCPClient:
    """Notion MCPクライアントのシングルトンインスタンスを取得します。"""
    global _notion_mcp_client
    if _notion_mcp_client is None:
        _notion_mcp_client = create_notion_mcp_client()
    return _notion_mcp_client


def create_session_manager(session_id: str, actor_id: str):
    """
    AgentCore Memory用のセッションマネージャーを作成します。

    Args:
        session_id: セッションID（グループIDまたはユーザーID）
        actor_id: アクターID（ユーザーID）

    Returns:
        AgentCoreMemorySessionManager または None（Memoryが未設定の場合）
    """
    if not AGENTCORE_MEMORY_ID:
        return None

    try:
        from bedrock_agentcore.memory.integrations.strands.config import (
            AgentCoreMemoryConfig,
            RetrievalConfig,
        )
        from bedrock_agentcore.memory.integrations.strands.session_manager import (
            AgentCoreMemorySessionManager,
        )

        # session_idは最低33文字必要
        # LINEのIDは通常33文字未満なので、プレフィックスを追加
        padded_session_id = f"ikitaitoko_bot_session_{session_id}".ljust(33, "_")
        padded_actor_id = f"ikitaitoko_bot_actor_{actor_id}".ljust(33, "_")

        config = AgentCoreMemoryConfig(
            memory_id=AGENTCORE_MEMORY_ID,
            session_id=padded_session_id,
            actor_id=padded_actor_id,
            retrieval_config={
                # 長期記憶からの検索設定
                "/preferences/{actorId}": RetrievalConfig(top_k=5, relevance_score=0.5),
                "/facts/{actorId}": RetrievalConfig(top_k=10, relevance_score=0.3),
                "/summaries/{actorId}/{sessionId}": RetrievalConfig(
                    top_k=3, relevance_score=0.5
                ),
            },
        )

        return AgentCoreMemorySessionManager(
            agentcore_memory_config=config,
            region_name=AGENTCORE_REGION,
        )

    except ImportError as e:
        logger.warning(f"AgentCore Memory not available: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to create session manager: {e}", exc_info=True)
        return None


def create_agent(session_id: Optional[str] = None, actor_id: Optional[str] = None) -> Agent:
    """
    エージェントを作成します。

    Args:
        session_id: セッションID（グループIDまたはユーザーID）
        actor_id: アクターID（ユーザーID）

    Returns:
        設定済みのAgentインスタンス
    """
    # MCPクライアントはシングルトンを使用（起動コストが高いため）
    notion_mcp = get_notion_mcp_client()

    # セッションマネージャーを作成（Memory設定がある場合のみ）
    session_manager = None
    if session_id and actor_id:
        session_manager = create_session_manager(session_id, actor_id)
        if session_manager:
            logger.info(f"Using AgentCore Memory with session_id={session_id}")

    return Agent(
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
        session_manager=session_manager,
    )


def invoke_agent(message: str, session_id: Optional[str] = None, actor_id: Optional[str] = None) -> str:
    """
    エージェントを呼び出してメッセージに対する応答を取得します。

    Args:
        message: ユーザーからのメッセージ
        session_id: セッションID（グループ/ルームID、またはDMの場合はユーザーID）
        actor_id: アクターID（ユーザーID）

    Returns:
        エージェントの応答テキスト
    """
    try:
        agent = create_agent(session_id, actor_id)
        result = agent(message)
        # AgentResultはstr()で変換するとテキストが得られる
        response_text = str(result)
        logger.info(f"Agent response: {response_text[:100]}...")
        return response_text
    except Exception as e:
        logger.error(f"Agent invocation failed: {e}", exc_info=True)
        return "申し訳ありません。処理中にエラーが発生しました。しばらくしてからもう一度お試しください。"


# LINE ハンドラーにエージェントコールバックを設定
line_handler.set_agent_callback(invoke_agent)


@app.route("/callback", methods=["POST"])
def callback():
    """LINE Webhookエンドポイント。"""
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    logger.info("Received webhook request")

    try:
        line_handler.handle_webhook(body, signature)
    except InvalidSignatureError:
        logger.warning("Invalid signature received")
        abort(400)
    except Exception as e:
        logger.error(f"Webhook handling failed: {e}", exc_info=True)
        abort(500)

    return "OK"


@app.route("/health", methods=["GET"])
def health():
    """ヘルスチェックエンドポイント。"""
    return {"status": "healthy"}


if __name__ == "__main__":
    # ローカル開発用
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=True)
