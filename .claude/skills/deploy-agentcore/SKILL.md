---
name: deploy-agentcore
description: |
  このスキルはユーザーが以下のように言った場合に使用してください：
  - 「デプロイして」「AgentCoreにデプロイ」「再デプロイして」
  - 「コード変更したからデプロイ」「変更を反映して」
  - 「AgentCoreのステータス確認」「デプロイ状況を確認」
  - 「agentcore deploy」の実行手順が知りたい
  AgentCore Runtimeへのコンテナデプロイ手順を提供します。
---

# AgentCore Deploy

ikitaitoko_botをAWS Bedrock AgentCore Runtimeにデプロイする手順。

## 前提条件

- AWS認証情報が設定済み（`.env`にAWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY）
- Dockerがインストール済み（コンテナビルド用）
- 必要な環境変数が`.env`に設定済み
- **重要**: AWS CLIコマンド（`aws logs tail`など）やagentcoreコマンドを実行する際は、必ず`.env`から環境変数を読み込むこと

## Agent IDの確認

Agent ID（例: `agentcore_app-XXXXXXXXXX`）は `agentcore status` の出力から確認できる。ログ確認やセッション管理で必要になる。

```bash
export $(grep -v '^#' .env | xargs) && uv run agentcore status
```

## デプロイ手順

### 1. 初回設定

```bash
uv run agentcore configure -e agentcore_app.py --deployment-type container --non-interactive
```

### 2. Dockerfileの更新

`.bedrock_agentcore/agentcore_app/Dockerfile`にNode.jsを追加:

```dockerfile
# Install Node.js for npx (Notion MCP server)
RUN apt-get update && \
    apt-get install -y nodejs npm && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Pre-install Notion MCP server globally
RUN npm install -g @notionhq/notion-mcp-server
```

### 3. デプロイ実行

```bash
export $(grep -v '^#' .env | xargs) && uv run agentcore deploy --local-build \
  --env NOTION_TOKEN="${NOTION_TOKEN}" \
  --env NOTION_DATABASE_ID="${NOTION_DATABASE_ID}" \
  --env NOTION_DATA_SOURCE_ID="${NOTION_DATA_SOURCE_ID}" \
  --env TAVILY_API_KEY="${TAVILY_API_KEY}"
```

### 4. ステータス確認

```bash
export $(grep -v '^#' .env | xargs) && uv run agentcore status
```

### 5. テスト

```bash
export $(grep -v '^#' .env | xargs) && uv run agentcore invoke '{"prompt": "行きたいところリストを見せて"}'
```

## 再デプロイ

コード変更後の再デプロイ:

```bash
# Dockerイメージキャッシュをクリア（必要な場合）
docker rmi $(docker images -q bedrock_agentcore-agentcore_app) 2>/dev/null || true

# 再デプロイ
export $(grep -v '^#' .env | xargs) && uv run agentcore deploy --local-build \
  --env NOTION_TOKEN="${NOTION_TOKEN}" \
  --env NOTION_DATABASE_ID="${NOTION_DATABASE_ID}" \
  --env NOTION_DATA_SOURCE_ID="${NOTION_DATA_SOURCE_ID}" \
  --env TAVILY_API_KEY="${TAVILY_API_KEY}"
```

### ローリングアップデートに関する注意

デプロイ後、古いコンテナがしばらく残ることがある（ローリングアップデート）。既存セッションが古いコンテナにルーティングされ、修正が反映されないケースがある。

対処法:
1. デプロイ後、数分待ってからテストする
2. 問題が続く場合はセッションをリセットする（下記「セッションリセット」を参照）

## ログ確認

`<AGENT_ID>`は`agentcore status`の出力から取得すること。

```bash
# リアルタイムログ
export $(grep -v '^#' .env | xargs) && aws logs tail /aws/bedrock-agentcore/runtimes/<AGENT_ID>-DEFAULT \
  --log-stream-name-prefix "$(date +%Y/%m/%d)/[runtime-logs" --follow

# 過去1時間のログ
export $(grep -v '^#' .env | xargs) && aws logs tail /aws/bedrock-agentcore/runtimes/<AGENT_ID>-DEFAULT \
  --log-stream-name-prefix "$(date +%Y/%m/%d)/[runtime-logs" --since 1h
```

## リソース削除

```bash
uv run agentcore destroy --force
```

## Memory管理

```bash
# Memory一覧
export $(grep -v '^#' .env | xargs) && AWS_DEFAULT_REGION=ap-northeast-1 uv run agentcore memory list

# Memory作成
uv run agentcore memory create <NAME> --strategies '[{"semanticMemoryStrategy": {"name": "semantic"}}]'

# Memory削除
uv run agentcore memory delete <MEMORY_ID>
```

## セッションリセット

エージェントのセッションメモリに過去のエラーが蓄積し、ツール使用を避けるなどの問題が起きた場合、セッションをリセットする。

```python
import boto3
client = boto3.client('bedrock-agentcore', region_name='ap-northeast-1')
client.stop_runtime_session(
    agentRuntimeArn='arn:aws:bedrock-agentcore:ap-northeast-1:<ACCOUNT_ID>:runtime/<AGENT_ID>',
    runtimeSessionId='<SESSION_ID>'
)
```

- `<AGENT_ID>`: `agentcore status`から取得
- `<ACCOUNT_ID>`: AWSアカウントID
- `<SESSION_ID>`: ログの`sessionId`から取得（LINEユーザーIDなど）

## トラブルシューティング

### モデルIDエラー

ap-northeast-1では`jp.`プレフィックスのモデルIDを使用:
- `jp.anthropic.claude-haiku-4-5-20251001-v1:0`
- `jp.anthropic.claude-sonnet-4-20250514-v1:0`

### MCPクライアント初期化エラー

コンテナにNode.jsがインストールされているか確認。Dockerfileを更新して再デプロイ。

### 環境変数エラー

`--env`フラグで必要な環境変数がすべて渡されているか確認。

### デプロイ後もエラーが直らない

1. ローリングアップデートで古いコンテナがまだ動いている可能性がある。数分待つ
2. セッションメモリに過去のエラーが蓄積し、エージェントがツール使用を避けている可能性がある。セッションをリセットする
3. ログでTool番号を確認する。新しいコンテナなら`Tool #1`から始まる。大きい番号の場合は古いコンテナ
