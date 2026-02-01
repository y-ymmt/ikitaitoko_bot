---
name: deploy-lambda
description: |
  Lambda + API GatewayによるLINE Webhook環境のTerraformデプロイ手順。
  使用タイミング: (1) 初回デプロイ、(2) コード変更後の再デプロイ、(3) 設定変更、(4) Webhook URLの確認、(5) リソースの削除
---

# Lambda Deploy

LINE Messaging API Webhook用のLambda + API Gateway環境をTerraformでデプロイする手順。

## アーキテクチャ

```
LINE Messaging API → API Gateway → Lambda → AgentCore Runtime → LINE Push Message
```

## 前提条件

- Terraform >= 1.0
- AWS CLI設定済み
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
cd terraform
terraform init
terraform apply
```

出力されるWebhook URLをLINE Developers Consoleに設定。

## 再デプロイ

```bash
cd terraform
terraform apply
```

## Webhook URL確認

```bash
cd terraform
terraform output webhook_url
```

## ログ確認

```bash
aws logs tail /aws/lambda/ikitaitoko-bot-webhook --follow
```

## リソース削除

```bash
cd terraform
terraform destroy
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
