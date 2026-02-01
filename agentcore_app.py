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
from strands_tools.http_request import http_request
from strands_tools.tavily import tavily_search

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
   - データベース情報を取得するには `API-retrieve-a-database` を使い、`database_id` に `{NOTION_DATABASE_ID}` を指定してください。

2. **新しい場所の追加**: ユーザーが「〇〇を追加して」「行きたいところリストに△△を入れて」と言った場合、
   Notionデータベースに新しいアイテムを作成します。
   - `API-post-page` を使用し、parentには `database_id`: `{NOTION_DATABASE_ID}` を指定してください。
   - 必要に応じてカテゴリ（旅行、飲食店、買い物、その他）や優先度（高・中・低）を確認してください。
   - データベースのプロパティ: 名前(title), 行った(checkbox), カテゴリ(select), 優先度(select), 場所(place), URL(url), メモ(rich_text)

3. **場所に関する情報検索**: 「〇〇について調べて」「△△の情報を教えて」と言われた場合、
   Web検索を行って情報を提供します。
   - 検索結果を要約して、わかりやすく伝えてください。

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
                http_request,
                tavily_search,
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
