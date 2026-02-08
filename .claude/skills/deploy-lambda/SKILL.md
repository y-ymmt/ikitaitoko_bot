---
name: deploy-lambda
description: |
  このスキルはユーザーが以下のように言った場合に使用してください：
  - 「Lambdaをデプロイして」「Lambda環境をデプロイ」
  - 「Webhook URLを確認して」「LINE Webhook設定」
  - 「Terraformでデプロイ」「terraform apply」
  - 「API Gatewayのデプロイ」「インフラをデプロイ」
  LINE Webhook用のLambda + API Gateway環境をTerraformでデプロイします。
---

# Lambda Deploy

LINE Messaging API Webhook用のLambda + API Gateway環境をTerraformでデプロイする手順。

## アーキテクチャ

```
LINE Messaging API → API Gateway → Lambda → AgentCore Runtime → LINE Push Message
```

## デプロイが必要なタイミング

- `lambda/handler.py` を変更した場合 → Lambdaの再デプロイが必要
- `terraform/` 配下のインフラ定義を変更した場合 → Terraformの再デプロイが必要
- `tools.py`、`agent.py`、`agentcore_app.py` のみの変更 → **Lambda側のデプロイは不要**（AgentCoreのみデプロイすればよい）

## 前提条件

- Terraform >= 1.0
- AWS認証情報が設定済み（`.env`にAWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY）
- AgentCore Runtimeがデプロイ済み

## ディレクトリ構成

```
ikitaitoko_bot/
├── lambda/
│   └── handler.py      # Lambda関数コード
└── terraform/
    ├── main.tf         # メインリソース定義
    ├── variables.tf    # 変数定義
    ├── outputs.tf      # 出力定義
    └── terraform.tfvars # 設定値（git管理外）
```

## 初回セットアップ

### 1. 設定ファイル作成

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
```

`terraform.tfvars`を編集:
- `line_channel_access_token`: LINE Developers Consoleから取得
- `line_channel_secret`: LINE Developers Consoleから取得
- `agentcore_runtime_id`: AgentCore Runtime ID

### 2. デプロイ

```bash
export $(grep -v '^#' .env | xargs) && cd terraform && terraform init && terraform apply
```

出力されるWebhook URLをLINE Developers Consoleに設定。

## 再デプロイ

```bash
export $(grep -v '^#' .env | xargs) && cd terraform && terraform apply -auto-approve
```

**重要**: `export $(grep -v '^#' .env | xargs)` でAWS認証情報を読み込まないとTerraformが認証エラーになる。

## Webhook URL確認

```bash
export $(grep -v '^#' .env | xargs) && cd terraform && terraform output webhook_url
```

## ログ確認

```bash
export $(grep -v '^#' .env | xargs) && aws logs tail /aws/lambda/ikitaitoko-bot-webhook --follow
```

## リソース削除

```bash
export $(grep -v '^#' .env | xargs) && cd terraform && terraform destroy
```

## トラブルシューティング

### 署名検証エラー

LINE_CHANNEL_SECRETが正しいか確認。

### AgentCore呼び出しエラー

1. AGENTCORE_RUNTIME_IDを確認
2. Lambda実行ロールにBedrock権限があるか確認
3. CloudWatch Logsでエラー詳細を確認

### タイムアウト

Lambda関数のタイムアウトは300秒（5分）に設定済み。AgentCoreの応答が遅い場合は増やす。

### No valid credential sources

Terraformコマンドの前に`export $(grep -v '^#' .env | xargs)`でAWS認証情報を読み込むこと。
