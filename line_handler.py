"""LINE Webhook handler for processing incoming messages."""

import logging
import threading
from typing import Optional

from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    PushMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import (
    Event,
    MessageEvent,
    TextMessageContent,
)

logger = logging.getLogger(__name__)


class LineHandler:
    """LINE Webhookイベントを処理するハンドラークラス。"""

    def __init__(self, channel_access_token: str, channel_secret: str):
        """
        LineHandlerを初期化します。

        Args:
            channel_access_token: LINEチャネルアクセストークン
            channel_secret: LINEチャネルシークレット
        """
        self.configuration = Configuration(access_token=channel_access_token)
        self.handler = WebhookHandler(channel_secret)
        self._agent_callback = None

        # イベントハンドラーを登録（ラムダでラップしてself参照を保持）
        @self.handler.add(MessageEvent, message=TextMessageContent)
        def handle_text_message(event, destination=None):
            self._handle_text_message(event, destination)

    def set_agent_callback(self, callback):
        """
        エージェントを呼び出すコールバック関数を設定します。

        Args:
            callback: メッセージを受け取りエージェントの応答を返す関数
        """
        self._agent_callback = callback

    def handle_webhook(self, body: str, signature: str) -> None:
        """
        Webhookリクエストを処理します。

        Args:
            body: リクエストボディ
            signature: X-Line-Signature ヘッダー値

        Raises:
            InvalidSignatureError: 署名が無効な場合
        """
        self.handler.handle(body, signature)

    def _is_bot_mentioned(self, event: MessageEvent) -> bool:
        """
        メッセージでBotがメンションされているかチェックします。

        Args:
            event: メッセージイベント

        Returns:
            Botがメンションされている場合True
        """
        # 1対1チャットの場合は常にTrue
        source_type = event.source.type if event.source else None
        if source_type == "user":
            return True

        # グループ/トークルームの場合はメンションをチェック
        message = event.message
        if not hasattr(message, "mention") or message.mention is None:
            return False

        # mentionees配列をチェック
        mentionees = message.mention.mentionees or []
        for mentionee in mentionees:
            # isSelfがTrueの場合、このBotへのメンション
            if getattr(mentionee, "is_self", False):
                return True

        return False

    def _extract_message_text(self, event: MessageEvent) -> str:
        """
        メンションを除去したメッセージテキストを抽出します。

        Args:
            event: メッセージイベント

        Returns:
            クリーンなメッセージテキスト
        """
        text = event.message.text

        # メンションがある場合は除去
        message = event.message
        if hasattr(message, "mention") and message.mention:
            mentionees = message.mention.mentionees or []
            # メンション部分を後ろから削除（インデックスがずれないように）
            for mentionee in sorted(
                mentionees, key=lambda m: m.index, reverse=True
            ):
                start = mentionee.index
                end = start + mentionee.length
                text = text[:start] + text[end:]

        # 余分な空白を整理
        text = " ".join(text.split()).strip()
        return text

    def _get_reply_to_id(self, event: MessageEvent) -> str:
        """
        返信先のIDを取得します（グループID、ルームID、またはユーザーID）。

        Args:
            event: メッセージイベント

        Returns:
            返信先ID
        """
        source = event.source
        if source.type == "group":
            return source.group_id
        elif source.type == "room":
            return source.room_id
        else:
            return source.user_id

    def _get_session_info(self, event: MessageEvent) -> tuple[str, str]:
        """
        セッション情報を取得します。

        Args:
            event: メッセージイベント

        Returns:
            (session_id, actor_id) のタプル
            - session_id: グループ/ルームの場合はそのID、DMの場合はユーザーID
            - actor_id: 常にユーザーID
        """
        source = event.source
        actor_id = source.user_id

        if source.type == "group":
            session_id = source.group_id
        elif source.type == "room":
            session_id = source.room_id
        else:
            # DMの場合はユーザーIDをセッションIDとして使用
            session_id = source.user_id

        return session_id, actor_id

    def _handle_text_message(self, event: MessageEvent, destination: str = None) -> None:
        """
        テキストメッセージイベントを処理します。
        処理はバックグラウンドスレッドで行い、即座にリターンします。

        Args:
            event: メッセージイベント
            destination: 宛先ID（LINE Bot SDK v3で追加）
        """
        # Botがメンションされているかチェック
        if not self._is_bot_mentioned(event):
            logger.debug("Bot was not mentioned, skipping message")
            return

        # メッセージテキストを抽出
        user_message = self._extract_message_text(event)
        if not user_message:
            logger.debug("Empty message after mention removal, skipping")
            return

        # 返信先IDを取得
        reply_to_id = self._get_reply_to_id(event)

        # セッション情報を取得（Memory用）
        session_id, actor_id = self._get_session_info(event)

        logger.info(f"Processing message: {user_message} (session={session_id})")

        # バックグラウンドスレッドで処理を実行
        thread = threading.Thread(
            target=self._process_message_async,
            args=(user_message, reply_to_id, session_id, actor_id),
            daemon=True,
        )
        thread.start()

    def _process_message_async(
        self, user_message: str, reply_to_id: str, session_id: str, actor_id: str
    ) -> None:
        """
        メッセージを非同期で処理します。

        Args:
            user_message: ユーザーメッセージ
            reply_to_id: 返信先ID
            session_id: セッションID（Memory用）
            actor_id: アクターID（Memory用）
        """
        try:
            # エージェントを呼び出して応答を取得
            if self._agent_callback:
                response_text = self._agent_callback(user_message, session_id, actor_id)
            else:
                response_text = "エージェントが設定されていません。"

            # LINEに応答を送信（push_message使用）
            self._push_message(reply_to_id, response_text)

        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            try:
                self._push_message(
                    reply_to_id,
                    "申し訳ありません。エラーが発生しました。しばらくしてからもう一度お試しください。",
                )
            except Exception as push_error:
                logger.error(f"Failed to send error message: {push_error}", exc_info=True)

    def _push_message(self, to: str, text: str) -> None:
        """
        LINEにテキストメッセージをプッシュ送信します。

        Args:
            to: 送信先ID（ユーザーID、グループID、またはルームID）
            text: 送信テキスト
        """
        # LINEメッセージの最大長は5000文字
        if len(text) > 5000:
            text = text[:4997] + "..."

        try:
            with ApiClient(self.configuration) as api_client:
                line_bot_api = MessagingApi(api_client)
                line_bot_api.push_message(
                    PushMessageRequest(
                        to=to,
                        messages=[TextMessage(text=text)],
                    )
                )
                logger.info(f"Message sent to {to}")
        except Exception as e:
            logger.error(f"Failed to push message: {e}", exc_info=True)
