# ikitaitoko_bot

LINE Botとして動作するAIエージェント。Notionの「行きたいところリスト」を管理し、場所に関する情報を検索できます。

## 機能

- **LINE Bot**: グループでメンションされると応答
- **Notion連携**: 行きたいところリストの参照・追加
- **Web検索**: Tavily Searchで場所に関する情報を検索

## 技術スタック

- [Strands Agents](https://strandsagents.com/) - AIエージェントフレームワーク
- [Amazon Bedrock](https://aws.amazon.com/bedrock/) - Claude モデル
- [Amazon Bedrock AgentCore](https://aws.github.io/bedrock-agentcore-starter-toolkit/) - デプロイ先
- [LINE Messaging API](https://developers.line.biz/ja/services/messaging-api/) - LINEボット
- [Notion MCP Server](https://github.com/makenotion/notion-mcp-server) - Notion連携

## セットアップ

### 1. 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

### 2. 環境変数の設定

`.env.example` を `.env` にコピーして、各値を設定してください。

```bash
cp .env.example .env
```

### 3. LINE Bot の作成

1. [LINE Developers Console](https://developers.line.biz/console/) にアクセス
2. 新しいプロバイダーを作成（または既存のものを選択）
3. 新しいMessaging APIチャネルを作成
4. チャネルシークレットとチャネルアクセストークンを取得
5. `.env` に設定

### 4. Notion Integration の作成

1. [Notion Integrations](https://www.notion.so/profile/integrations) にアクセス
2. 新しいIntegrationを作成
3. Integration Tokenを取得
4. 対象のNotionデータベースでIntegrationを接続
5. データベースIDを取得（URLの `notion.so/` と `?v=` の間の部分）
6. `.env` に設定

### 5. Tavily API キーの取得

1. [Tavily](https://tavily.com/) でアカウント作成
2. APIキーを取得
3. `.env` に設定

### 6. AWS 設定

1. AWSアカウントを用意
2. Bedrock Claudeモデルへのアクセスを有効化
3. IAMユーザー/ロールを作成
4. `.env` に認証情報を設定

## 実行方法

### ローカル開発

```bash
python agent.py
```

サーバーが `http://localhost:8080` で起動します。

LINE Webhookをテストするには、[ngrok](https://ngrok.com/) などでトンネルを作成してください：

```bash
ngrok http 8080
```

表示されたURLを LINE Developers Console の Webhook URL に設定します。

### AgentCore へのデプロイ

```bash
# AgentCore CLI をインストール
pip install bedrock-agentcore-starter-toolkit

# 設定（インタラクティブモードでMemory設定も行えます）
agentcore configure -e agentcore_app.py

# デプロイ
agentcore deploy

# ステータス確認（Memoryのプロビジョニングには2〜5分かかります）
agentcore status

# テスト
agentcore invoke '{"prompt": "行きたいところリストを見せて"}'

# 削除（不要になった場合）
agentcore destroy
```

### Lambda + API Gateway によるLINE Webhook のデプロイ

AgentCore RuntimeはHTTPエンドポイントを直接公開しないため、Lambda + API GatewayでLINE Webhookを受け取り、AgentCoreを呼び出します。

#### 1. Terraform設定

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

`terraform.tfvars` を編集:

```hcl
aws_region                = "ap-northeast-1"
project_name              = "ikitaitoko-bot"
line_channel_access_token = "YOUR_LINE_CHANNEL_ACCESS_TOKEN"
line_channel_secret       = "YOUR_LINE_CHANNEL_SECRET"
agentcore_runtime_id      = "agentcore_app-XXXXX"  # agentcore statusで確認
```

#### 2. デプロイ

```bash
terraform init
terraform apply
```

#### 3. LINE Webhook URLの設定

1. Terraformの出力に表示される `webhook_url` をコピー
2. [LINE Developers Console](https://developers.line.biz/console/) にアクセス
3. 対象のMessaging APIチャネルを選択
4. Messaging API設定 > Webhook URL に設定
5. 「検証」ボタンで動作確認
6. Webhookを有効化

#### 4. 再デプロイ

コード変更後:

```bash
cd terraform
terraform apply
```

#### 5. リソース削除

```bash
cd terraform
terraform destroy
```

### AgentCore Memory の管理

会話履歴を保持するためのMemoryリソースを管理できます。

```bash
# Memory作成（短期+長期メモリ、セマンティック検索有効）
agentcore memory create IkitaitokoBot_Memory \
  --description "LINE Bot ikitaitoko list memory" \
  --strategies '[{"name": "semanticLongTermMemory"}]'

# Memory一覧
agentcore memory list

# Memory詳細確認
agentcore memory get <MEMORY_ID>

# Memoryステータス確認
agentcore memory status <MEMORY_ID>

# Memory削除
agentcore memory delete <MEMORY_ID>
```

作成後、表示された `MEMORY_ID` を `.env` の `AGENTCORE_MEMORY_ID` に設定してください。

## 使い方

LINE グループで Bot をメンションして話しかけてください：

- `@Bot 行きたいところリストを見せて` - リスト一覧を表示
- `@Bot 京都を追加して` - 新しい場所を追加
- `@Bot 箱根の温泉について教えて` - 場所の情報を検索

## プロジェクト構成

```
ikitaitoko_bot/
├── agent.py              # ローカル実行用（Flask + LINE Webhook）
├── agentcore_app.py      # AgentCore Runtime用エントリポイント
├── requirements.txt      # Python依存パッケージ
├── .env.example          # 環境変数テンプレート
├── lambda/
│   └── handler.py        # LINE Webhook Lambda関数
├── terraform/
│   ├── main.tf           # Terraformリソース定義
│   ├── variables.tf      # 変数定義
│   ├── outputs.tf        # 出力定義
│   └── terraform.tfvars.example
└── README.md
```

## ライセンス

MIT
