---
name: deploy
description: |
  AgentCore Runtimeへのデプロイ手順。コンテナデプロイでNode.js/MCPを含む環境を構築し、Notion連携機能を動作させる。
  使用タイミング: (1) AgentCoreへの新規デプロイ、(2) コード変更後の再デプロイ、(3) デプロイ設定の確認、(4) リソースの削除
---

# AgentCore Deploy

ikitaitoko_botをAWS Bedrock AgentCore Runtimeにデプロイする手順。

## 前提条件

- AWS認証情報が設定済み（`.env`にAWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY）
- Dockerがインストール済み（コンテナビルド用）
- 必要な環境変数が`.env`に設定済み

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
uv run agentcore status
```

### 5. テスト

```bash
uv run agentcore invoke '{"prompt": "行きたいところリストを見せて"}'
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

## ログ確認

```bash
# リアルタイムログ
aws logs tail /aws/bedrock-agentcore/runtimes/<AGENT_ID>-DEFAULT \
  --log-stream-name-prefix "$(date +%Y/%m/%d)/[runtime-logs" --follow

# 過去1時間のログ
aws logs tail /aws/bedrock-agentcore/runtimes/<AGENT_ID>-DEFAULT \
  --log-stream-name-prefix "$(date +%Y/%m/%d)/[runtime-logs" --since 1h
```

## リソース削除

```bash
uv run agentcore destroy --force
```

## Memory管理

```bash
# Memory一覧
uv run agentcore memory list

# Memory作成
uv run agentcore memory create <NAME> --strategies '[{"semanticMemoryStrategy": {"name": "semantic"}}]'

# Memory削除
uv run agentcore memory delete <MEMORY_ID>
```

## トラブルシューティング

### モデルIDエラー

ap-northeast-1では`jp.`プレフィックスのモデルIDを使用:
- `jp.anthropic.claude-haiku-4-5-20251001-v1:0`
- `jp.anthropic.claude-sonnet-4-20250514-v1:0`

### MCPクライアント初期化エラー

コンテナにNode.jsがインストールされているか確認。Dockerfileを更新して再デプロイ。

### 環境変数エラー

`--env`フラグで必要な環境変数がすべて渡されているか確認。
