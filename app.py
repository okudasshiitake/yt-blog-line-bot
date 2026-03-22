"""
🤖 YouTube → ブログ自動生成 LINE Bot（クラウド版）
Render等にデプロイしてスマホだけで使える！

必要な環境変数:
  GEMINI_API_KEY, LINE_CHANNEL_SECRET, LINE_CHANNEL_ACCESS_TOKEN
  SHOP_NAME, PERSONA, FIRST_PERSON, TONE, PRODUCTS
"""
import os
import re
import json
import time
import threading
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi,
    ReplyMessageRequest, PushMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.v3.exceptions import InvalidSignatureError
from blog_engine import load_config, init_api, download_video, generate_article, postprocess_body

USER_SETTINGS_FILE = "user_settings.json"

# ---------- 初期化 ----------
app = Flask(__name__)

LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "")
OWNER_LINE_ID = os.getenv("OWNER_LINE_ID", "")  # 設定すると本人だけが使える鍵

handler = WebhookHandler(LINE_CHANNEL_SECRET)
configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)

config = load_config()
init_api()

# 同時処理を防ぐロック（1件ずつ処理）
_processing_lock = threading.Lock()


# ---------- ユーザー設定（モード切替）の管理 ----------
def load_user_settings(user_id: str) -> str:
    """ユーザーのカスタム指示を読み込む"""
    if os.path.exists(USER_SETTINGS_FILE):
        try:
            with open(USER_SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get(user_id, "")
        except Exception:
            return ""
    return ""

def save_user_settings(user_id: str, text: str):
    """ユーザーのカスタム指示を保存・削除する"""
    data = {}
    if os.path.exists(USER_SETTINGS_FILE):
        try:
            with open(USER_SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass

    if text:
        data[user_id] = text
    else:
        if user_id in data:
            del data[user_id]

    try:
        with open(USER_SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass


# ---------- ユーティリティ ----------
def is_youtube_url(text: str) -> bool:
    """YouTube URL かどうか判定する"""
    patterns = [
        r"https?://(www\.)?youtube\.com/watch",
        r"https?://(www\.)?youtube\.com/shorts/",
        r"https?://youtu\.be/",
    ]
    return any(re.search(p, text) for p in patterns)


def split_message(text: str, max_len: int = 4500) -> list[str]:
    """LINE の文字数制限（5000字）に収まるように分割"""
    if len(text) <= max_len:
        return [text]

    parts: list[str] = []
    while text:
        if len(text) <= max_len:
            parts.append(text)
            break
        pos = text.rfind("\n", 0, max_len)
        if pos == -1:
            pos = max_len
        parts.append(text[:pos])
        text = text[pos:].lstrip("\n")
    return parts


def push_text(line_api: MessagingApi, user_id: str, text: str):
    """テキストを push_message で送信（長ければ自動分割）"""
    for part in split_message(text):
        line_api.push_message(
            PushMessageRequest(to=user_id, messages=[TextMessage(text=part)])
        )
        time.sleep(0.3)


# ---------- 動画処理（バックグラウンドスレッド） ----------
def process_video(user_id: str, url: str):
    """動画ダウンロード → AI記事生成 → LINE送信"""
    if not _processing_lock.acquire(blocking=False):
        with ApiClient(configuration) as api_client:
            api = MessagingApi(api_client)
            push_text(api, user_id, "⏳ 現在別の動画を処理中です。少し待ってから再送してください。")
        return

    temp_video = None
    try:
        with ApiClient(configuration) as api_client:
            api = MessagingApi(api_client)

            # --- 1. ダウンロード ---
            push_text(api, user_id, "📥 動画をダウンロード中...")
            temp_video = download_video(url)

            # --- 2. AI 記事生成 ---
            push_text(api, user_id, "🤖 AIが記事を執筆中... (1〜2分かかります)")
            user_instruction = load_user_settings(user_id)
            article = generate_article(temp_video, config, user_instruction)

            titles = article.get("titles", ["無題の記事"])
            if isinstance(titles, str):
                titles = [titles]
            body = article.get("body", "")
            hashtags = article.get("hashtags", [])

            # --- 3. 後処理 ---
            body = postprocess_body(body, url, config)

            # --- 4. 結果送信 ---
            title_text = "\n\n".join([f"案{i+1}: {t}" for i, t in enumerate(titles)])
            hashtag_text = " ".join(hashtags) if hashtags else ""

            header = (
                f"✨ 記事が完成しました！\n\n"
                f"📝 【選べるタイトル3案】\n{title_text}\n\n"
                f"{'─' * 20}\n\n"
            )
            
            # 本文の送信
            push_text(api, user_id, header + body)

            # ハッシュタグの送信
            if hashtag_text:
                push_text(
                    api, user_id,
                    f"🏷️ 【おすすめSNSハッシュタグ】\n動画の告知やSNS投稿に使ってね！\n\n{hashtag_text}"
                )

            push_text(
                api, user_id,
                "💡 上の中から好きなタイトルを選んで、ブログに貼り付けてください！",
            )

    except Exception as e:
        try:
            with ApiClient(configuration) as api_client:
                api = MessagingApi(api_client)
                push_text(api, user_id, f"❌ エラーが発生しました:\n{str(e)[:500]}")
        except Exception:
            pass
    finally:
        # 一時ファイルを必ず削除（ディスク節約）
        if temp_video and os.path.exists(temp_video):
            os.remove(temp_video)
        _processing_lock.release()


# ---------- Webhook ----------
@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"


@app.route("/", methods=["GET"])
def health():
    """ヘルスチェック用（Renderのkeep-alive等）"""
    return f"🤖 {config.get('shop_name', 'Blog Bot')} is running!"


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    text = event.message.text.strip()
    user_id = event.source.user_id

    # ログにユーザーIDを表示（初回確認用）
    print(f"📩 メッセージ受信 | user_id: {user_id} | text: {text[:30]}")

    with ApiClient(configuration) as api_client:
        api = MessagingApi(api_client)

        # --- オーナー制限チェック ---
        if OWNER_LINE_ID and user_id != OWNER_LINE_ID:
            api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[
                        TextMessage(
                            text="🔒 このBotは非公開です。"
                        )
                    ],
                )
            )
            return

        if is_youtube_url(text):
            api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[
                        TextMessage(
                            text=(
                                "🎬 動画を受け取りました！\n\n"
                                "ダウンロード → AI執筆\n"
                                "を開始します。\n\n"
                                "完了まで1〜2分お待ちください ⏳"
                            )
                        )
                    ],
                )
            )
            t = threading.Thread(target=process_video, args=(user_id, text), daemon=True)
            t.start()
        elif text == "リセット":
            save_user_settings(user_id, "")
            api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[
                        TextMessage(
                            text=(
                                "🔄 カスタム設定をリセットしました！\n"
                                "次回からは初期設定（Renderの設定）で記事を作成します。"
                            )
                        )
                    ],
                )
            )
        else:
            save_user_settings(user_id, text)
            api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[
                        TextMessage(
                            text=(
                                "🤖 カスタム指示（モード）を設定しました！\n\n"
                                f"「{text[:50]}...」\n\n"
                                "次回からの動画は、この指示を最優先して記事を作成します✍️\n\n"
                                "（☝️元に戻すときは「リセット」と送ってください）"
                            )
                        )
                    ],
                )
            )

# ---------- 起動 ----------
if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    print("=" * 40)
    print("🤖 LINE Bot ブログ生成サーバー起動中...")
    print(f"📡 ポート: {port}")
    print(f"📦 ショップ: {config.get('shop_name', '未設定')}")
    print("=" * 40)
    app.run(host="0.0.0.0", port=port, debug=False)
