"""
🎬 YouTube → ブログ記事 AI生成エンジン（クラウド版）
環境変数から設定を読み込み、PC不要でLINEだけで完結。
"""
import os
import re
import json
import time
import tempfile
import yt_dlp
import google.generativeai as genai


# ========== 設定の読み込み（環境変数から） ==========
def load_config() -> dict:
    """環境変数からショップ設定を読み込む"""
    products_raw = os.getenv("PRODUCTS", "")
    products = [p.strip() for p in products_raw.split(",") if p.strip()]

    not_selling_raw = os.getenv("NOT_SELLING", "")
    not_selling = [p.strip() for p in not_selling_raw.split(",") if p.strip()]

    return {
        "shop_name": os.getenv("SHOP_NAME", "あなたのお店"),
        "persona": os.getenv("PERSONA", "店長"),
        "first_person": os.getenv("FIRST_PERSON", "私"),
        "tone": os.getenv("TONE", "カジュアル"),
        "products": products,
        "not_selling": not_selling,
        "platform": os.getenv("PLATFORM", "BASE"),
        "model": os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
        "temperature": float(os.getenv("TEMPERATURE", "0.8")),
        "title_max_chars": int(os.getenv("TITLE_MAX_CHARS", "50")),
        "custom_rules": os.getenv("CUSTOM_RULES", ""),
    }


def init_api():
    """Gemini APIを初期化する"""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY が設定されていません。")
    genai.configure(api_key=api_key)


# ========== 動画ダウンロード ==========
def download_video(url: str) -> str:
    """YouTubeから動画をダウンロードし、一時ファイルパスを返す"""
    tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
    tmp.close()

    ydl_opts = {
        "format": "worst[ext=mp4]",  # クラウド向け：最小サイズ
        "outtmpl": tmp.name,
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])
    return tmp.name


# ========== AI記事生成 ==========
def build_system_prompt(config: dict) -> str:
    """設定からAIへのシステムプロンプトを組み立てる"""
    shop_name = config["shop_name"]
    persona = config["persona"]
    first_person = config["first_person"]
    products = config["products"]
    not_selling = config["not_selling"]
    title_max = config["title_max_chars"]
    platform = config["platform"]

    tone = config["tone"]
    tone_map = {
        "エンタメ": "ねとらぼ等のエンタメ系WEBメディアの敏腕ライターレベルの、読者を爆笑させてツッコませる構成力",
        "カジュアル": "友達に話しかけるような親しみやすいカジュアルな文体",
        "丁寧": "丁寧で信頼感のある、プロフェッショナルな文体",
    }
    tone_desc = tone_map.get(tone, tone_map["カジュアル"])

    products_text = "\n".join([f"・{p}" for p in products]) if products else "・（未設定）"
    not_selling_text = ""
    if not_selling:
        items = "、".join(not_selling)
        not_selling_text = f"\n※以下は販売していません：{items}"

    custom_rules_section = ""
    if config.get("custom_rules"):
        custom_rules_section = f"\n【独自の特別執筆ルール（最優先）】\n{config['custom_rules']}\n"

    return f"""
【あなたの役割（ペルソナ）】
あなたは「{shop_name}」の『{persona}本人』です。ブログの語り手として、一人称「{first_person}」を使用し、ユーモア溢れる親しみやすいトーンで語りかけてください。
※ただし、文章の執筆スキルは{tone_desc}を持って執筆してください。（※作中で自分がライターや編集長であると自称・名乗る必要は一切ありません。あくまで{persona}として振る舞ってください。）
アップロードされた動画の内容を元に、最高に面白くて読者の目を惹き、つい商品をポチりたくなる{platform}ブログ用の記事を作成してください。
{custom_rules_section}
【構成ルール】
1. タイトルは絶対に【{title_max}文字以内】に厳守しつつ、キャッチーで思わずクリックしたくなるものにすること。
2. 動画内の出来事、特にハプニングや失敗があれば、それを「最高のオチ」として大げさにエンタメへ昇華させる。
3. ★改行ルール（超重要）★ 文章がぎゅうぎゅう詰めにならないよう、段落ごと・話題の転換ごとに【必ず2〜3行の空行】を入れること。1文ごとに改行しても構わないくらい、たっぷりスペースを使って読みやすくすること。絵文字や「【】」「◆」などの全角記号を使って見やすく装飾する。（※{platform}にそのままコピペするため、アスタリスク「**」やシャープ「#」などのMarkdown記法は一切使わないこと。プレーンテキストで出力する。）
4. 画像挿入指示は不要です。テキストのみで出力してください。
5. ★重要★ {shop_name}の商品宣伝： 記事の終盤に、必ず「◆◆ {shop_name}からのお知らせ ◆◆」という見出し行を書き、その【後に】商品紹介の文を続けてください。見出しの前に商品紹介を書き始めないこと。動画内容に自然に絡めて、{persona}らしいおどけた感じで紹介してください。
【実際に販売している商品一覧（これ以外の商品を捏造しないこと！）】
{products_text}{not_selling_text}
6. ★重要★ アクションの促進： 最下部で、次回の動画やブログ実験の期待を煽り、YouTubeやBASEアプリのショップフォローを促す一言を入れてください。
7. ★禁止事項★ 記事本文中に「（宣伝も忘れない）」「（ここで宣伝です）」「（さりげなく宣伝）」のような、宣伝をしていることへのメタ発言・心の声・楽屋ネタは一切入れないこと。宣伝はあくまで自然に、読者に語りかける形でさらっと行う。

【出力形式】
必ず以下のJSONフォーマット（Markdownコードブロックなしの生のJSON文字列のみ）で出力し、他の文字は含めないこと。
{{
    "title": "{title_max}文字以内の記事タイトル",
    "body": "Markdownを使わない、空行をたっぷり入れたプレーンテキストの記事本文"
}}
"""


def generate_article(video_path: str, config: dict) -> dict:
    """動画をGemini AIに渡し、ブログ記事を生成する"""
    video_file = genai.upload_file(path=video_path)

    while video_file.state.name == "PROCESSING":
        time.sleep(5)
        video_file = genai.get_file(video_file.name)

    if video_file.state.name == "FAILED":
        raise RuntimeError("動画の処理に失敗しました。")

    system_instruction = build_system_prompt(config)
    model_name = config.get("model", "gemini-2.0-flash")
    temperature = config.get("temperature", 0.8)

    model = genai.GenerativeModel(
        model_name=model_name,
        system_instruction=system_instruction,
        generation_config={
            "response_mime_type": "application/json",
            "temperature": temperature,
        },
    )

    response = model.generate_content(
        [video_file, "この動画を元に、指示通りのJSONフォーマットでブログ記事を出力してください。"]
    )

    try:
        data = json.loads(response.text)
        genai.delete_file(video_file.name)
        if isinstance(data, list) and len(data) > 0:
            data = data[0]
        return data
    except json.JSONDecodeError:
        genai.delete_file(video_file.name)
        raise RuntimeError(f"AIの出力がJSON形式ではありませんでした: {response.text[:200]}")


# ========== 後処理 ==========
def normalize_youtube_url(url: str) -> str:
    """ショート等のURLを標準YouTube URLに変換する"""
    m = re.search(r"(?:v=|/shorts/|youtu\.be/)([^&?]+)", url)
    if m:
        return f"https://www.youtube.com/watch?v={m.group(1)}"
    return url


def postprocess_body(body: str, url: str, config: dict) -> str:
    """本文にYouTube URL挿入と空行調整を行う"""
    shop_name = config.get("shop_name", "お店")

    base_friendly_url = normalize_youtube_url(url)
    youtube_block = f"\n\n\n◆ 今回の元動画はこちら！\n{base_friendly_url}\n\n\n"

    promo_markers = [f"◆◆ {shop_name}", "◆◆ お知らせ", "◆◆ 商品"]
    inserted = False
    for marker in promo_markers:
        if marker in body:
            body = body.replace(marker, youtube_block + marker, 1)
            inserted = True
            break
    if not inserted:
        body += youtube_block

    return body
