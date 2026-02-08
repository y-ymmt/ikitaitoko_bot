"""
LINE Webhook Handler for ikitaitoko_bot

LINE WebhookをLambdaで受け取り、AgentCore Runtimeを呼び出して応答を返します。
"""

import json
import os
import hmac
import hashlib
import base64
import urllib.request
import boto3


def lambda_handler(event, context):
    """Lambda エントリーポイント"""
    try:
        # API Gateway からのリクエストを処理
        body = event.get('body', '')
        if event.get('isBase64Encoded', False):
            body = base64.b64decode(body).decode('utf-8')

        headers = event.get('headers', {})
        # ヘッダーは小文字で正規化されている場合がある
        signature = headers.get('x-line-signature') or headers.get('X-Line-Signature', '')

        # 署名検証
        if not verify_signature(body, signature):
            print('Invalid signature')
            return {'statusCode': 200, 'body': json.dumps({'status': 'invalid signature'})}

        # Webhookデータをパース
        webhook_data = json.loads(body)
        events = webhook_data.get('events', [])

        # イベントがない場合（検証リクエスト等）
        if not events:
            return {'statusCode': 200, 'body': json.dumps({'status': 'ok'})}

        # 各イベントを処理
        for evt in events:
            try:
                process_event(evt)
            except Exception as e:
                print(f'Error processing event: {e}')

        return {'statusCode': 200, 'body': json.dumps({'status': 'ok'})}

    except Exception as e:
        print(f'Error processing webhook: {e}')
        return {'statusCode': 200, 'body': json.dumps({'status': 'ok'})}


def verify_signature(body: str, signature: str) -> bool:
    """LINE署名を検証"""
    if not signature:
        print('No signature provided')
        return False

    channel_secret = os.environ.get('LINE_CHANNEL_SECRET', '')
    if not channel_secret:
        print('LINE_CHANNEL_SECRET not configured')
        return False

    hash_value = hmac.new(
        channel_secret.encode('utf-8'),
        body.encode('utf-8'),
        hashlib.sha256
    ).digest()
    expected_signature = base64.b64encode(hash_value).decode('utf-8')

    return hmac.compare_digest(signature, expected_signature)


def process_event(event: dict):
    """イベントを処理"""
    if event.get('type') != 'message':
        return

    message = event.get('message', {})
    message_type = message.get('type')

    # 位置情報メッセージの処理
    if message_type == 'location':
        user_message = extract_location_text(message)
    elif message_type == 'text':
        # Botがメンションされているかチェック
        if not is_bot_mentioned(event):
            print('Bot was not mentioned, skipping')
            return
        user_message = extract_message_text(event)
    else:
        return

    if not user_message:
        print('Empty message, skipping')
        return

    reply_to_id = get_reply_to_id(event)
    session_id = get_session_id(event)

    print(f'Processing message: {user_message} (session={session_id})')

    try:
        # AgentCoreを呼び出し
        response_text = invoke_agent_core(user_message, session_id)
        # LINEに応答を送信
        push_message(reply_to_id, response_text)
    except Exception as e:
        print(f'Error processing message: {e}')
        try:
            push_message(reply_to_id, '申し訳ありません。エラーが発生しました。しばらくしてからもう一度お試しください。')
        except Exception as push_error:
            print(f'Failed to send error message: {push_error}')


def is_bot_mentioned(event: dict) -> bool:
    """Botがメンションされているかチェック"""
    source = event.get('source', {})
    source_type = source.get('type')

    # 1対1チャットの場合は常にTrue
    if source_type == 'user':
        return True

    # グループ/トークルームの場合はメンションをチェック
    message = event.get('message', {})
    mention = message.get('mention')
    if not mention:
        return False

    mentionees = mention.get('mentionees', [])
    for mentionee in mentionees:
        if mentionee.get('isSelf') is True:
            return True

    return False


def extract_message_text(event: dict) -> str:
    """メンションを除去したメッセージテキストを抽出"""
    message = event.get('message', {})
    text = message.get('text', '')

    mention = message.get('mention')
    if mention:
        mentionees = mention.get('mentionees', [])
        # メンション部分を後ろから削除（インデックスがずれないように）
        sorted_mentionees = sorted(mentionees, key=lambda x: x.get('index', 0), reverse=True)
        for mentionee in sorted_mentionees:
            start = mentionee.get('index', 0)
            length = mentionee.get('length', 0)
            text = text[:start] + text[start + length:]

    # 余分な空白を整理
    return ' '.join(text.split()).strip()


def extract_location_text(message: dict) -> str:
    """位置情報メッセージをテキストに変換"""
    title = message.get('title', '')
    address = message.get('address', '')
    latitude = message.get('latitude')
    longitude = message.get('longitude')

    parts = ['ユーザーが現在地を共有しました。']
    if title:
        parts.append(f'場所名: {title}')
    if address:
        parts.append(f'住所: {address}')
    if latitude is not None and longitude is not None:
        parts.append(f'緯度: {latitude}, 経度: {longitude}')

    return '\n'.join(parts)


def get_reply_to_id(event: dict) -> str:
    """返信先IDを取得"""
    source = event.get('source', {})
    source_type = source.get('type')

    if source_type == 'group':
        return source.get('groupId')
    elif source_type == 'room':
        return source.get('roomId')
    else:
        return source.get('userId')


def get_session_id(event: dict) -> str:
    """セッションIDを取得"""
    source = event.get('source', {})
    source_type = source.get('type')

    if source_type == 'group':
        return source.get('groupId')
    elif source_type == 'room':
        return source.get('roomId')
    else:
        return source.get('userId')


def invoke_agent_core(prompt: str, session_id: str) -> str:
    """AgentCore Runtimeを呼び出し（boto3使用）"""
    import uuid

    runtime_id = os.environ.get('AGENTCORE_RUNTIME_ID', '')
    region = os.environ.get('AWS_REGION_NAME', 'ap-northeast-1')

    # AgentCore Runtime ARNを構築
    # runtime_idが "agentcore_app-HCZHQWA4oU" の形式の場合
    account_id = boto3.client('sts').get_caller_identity()['Account']
    runtime_arn = f'arn:aws:bedrock-agentcore:{region}:{account_id}:runtime/{runtime_id}'

    # セッションIDは33文字以上必要
    if len(session_id) < 33:
        session_id = session_id + '-' + str(uuid.uuid4())[:16]

    client = boto3.client('bedrock-agentcore', region_name=region)

    print(f'Invoking AgentCore: arn={runtime_arn}, session={session_id}')

    response = client.invoke_agent_runtime(
        agentRuntimeArn=runtime_arn,
        contentType='application/json',
        accept='application/json',
        runtimeSessionId=session_id,
        payload=json.dumps({'prompt': prompt}).encode('utf-8')
    )

    # StreamingBodyを読み込む
    body_content = response['response'].read().decode('utf-8')
    print(f'AgentCore response: {body_content}')

    # JSONとしてパース
    result = json.loads(body_content)
    return result.get('result', body_content)


def push_message(to: str, text: str):
    """LINEにプッシュメッセージを送信"""
    access_token = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', '')

    # LINEメッセージの最大長は5000文字
    if len(text) > 5000:
        text = text[:4997] + '...'

    payload = {
        'to': to,
        'messages': [{'type': 'text', 'text': text}]
    }

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {access_token}'
    }

    req = urllib.request.Request(
        'https://api.line.me/v2/bot/message/push',
        data=json.dumps(payload).encode('utf-8'),
        headers=headers,
        method='POST'
    )

    try:
        with urllib.request.urlopen(req) as response:
            if response.status != 200:
                raise Exception(f'LINE API returned {response.status}')
            print(f'Message sent to {to}')
    except urllib.error.HTTPError as e:
        print(f'Failed to push message: {e.read().decode()}')
        raise
