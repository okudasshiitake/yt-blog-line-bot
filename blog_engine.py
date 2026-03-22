"""
🎬 YouTube → ブログ記事 AI生成エンジン（クラウド版）
環境変数から設定を読み込み、PC不要でLINEだけで完結。
YouTube URLをGemini AIに直接渡す方式（ダウンロード不要）。
"""
import os
import re
import json

from google import genai
from google.genai import types


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
        "model": os.getenv("GEMINI_MODEL", "gemini-3.0-flash"),
        "temperature": float(os.getenv("TEMPERATURE", "0.8")),
        "title_max_chars": int(os.getenv("TITLE_MAX_CHARS", "50")),
        "custom_rules": os.getenv("CUSTOM_RULES", ""),
    }


# ========== Gemini API クライアント ==========
_client = None


def get_client():
    """Gemini APIクライアントを取得"""
    global _client
    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY が設定されていません。")
        _client = genai.Client(api_key=api_key)
    return _client


def init_api():
    """Gemini APIを初期化する"""
    get_client()


# ========== YouTube URL直接方式（メイン） ==========
def normalize_youtube_url(url: str) -> str:
    """ショート等のURLを標準YouTube URLに変換する"""
    m = re.search(r"(?:v=|/shorts/|youtu\.be/)([^&?]+)", url)
    if m:
        return f"https://www.youtube.com/watch?v={m.group(1)}"
    return url


def generate_article_from_url(url: str, config: dict, user_instruction: str = "") -> dict:
    """YouTube URLをGemini AIに直接渡して記事を生成（ダウンロード不要！）"""
    client = get_client()
    system_instruction = build_system_prompt(config, user_instruction)
    model_name = config.get("model", "gemini-2.0-flash")
    temperature = config.get("temperature", 0.8)

    standard_url = normalize_youtube_url(url)

    response = client.models.generate_content(
        model=model_name,
        contents=[
            types.Content(
                parts=[
                    types.Part.from_uri(
                        file_uri=standard_url,
                        mime_type="video/*",
                    ),
                    types.Part.from_text(
                        "この動画を元に、システム指示通りのJSONフォーマットでブログ記事を出力してください。"
                    ),
                ]
            )
        ],
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            temperature=temperature,
        ),
    )

    try:
        data = json.loads(response.text)
        if isinstance(data, list) and len(data) > 0:
            data = data[0]
        return data
    except json.JSONDecodeError:
        raise RuntimeError(f"AIの出力がJSON形式ではありませんでした: {response.text[:200]}")


# ========== システムプロンプト生成 ==========
def build_system_prompt(config: dict, user_instruction: str = "") -> str:
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
        custom_rules_section = f"\n【デフォルトの特別執筆ルール】\n{config['custom_rules']}\n"

    user_instruction_section = ""
    if user_instruction:
        user_instruction_section = f"\n【★★★ 最優先・LINEからの上書き指示 ★★★】\n以下のユーザーからの指示を最も優先して適用してください（店名・文体・除外ルールの変更や別のモードの指定があればこれに従うこと）：\n{user_instruction}\n"

    header = f"""
【あなたの役割（ペルソナ）】
あなたは「{shop_name}」の『{persona}本人』です。ブログの語り手として、一人称「{first_person}」を使用し、ユーモア溢れる親しみやすいトーンで語りかけてください。
※ただし、文章の執筆スキルは{tone_desc}を持って執筆してください。（※作中で自分がライターや編集長であると自称・名乗る必要は一切ありません。あくまで{persona}として振る舞ってください。）
アップロードされた動画の内容を元に、最高に面白くて読者の目を惹く{platform}用の記事を作成してください。
{custom_rules_section}{user_instruction_section}"""

    if platform.lower() == "note":
        rules = f"""
【構成ルール（note特化版）】
1. タイトルは絶対に【{title_max}文字以内】に厳守しつつ、全くテイストの違う3パターンのタイトル案（①クリック重視の煽り系、②Google検索SEO重視、③SNS向けのおもしろ系）を提案してください。
2. ★冒頭のつかみ（超重要）★ noteではタイムラインや検索結果で最初の数行のみ表示される。記事の冒頭1〜2文で「え、なにそれ？」「続きが気になる！」と思わせる強烈なフックを必ず入れること。
3. ★リッチテキスト★ noteはMarkdownに近いリッチテキストに対応しています。以下を積極的に使って、noteの画面上で映える「読みたくなるデザイン」に仕上げてください：
   - 見出し: 「## 見出し」
   - 太字: 「**強調したい言葉**」
   - 引用: 「> 引用文」
   - 箇条書き: 「- 項目」
   - 区切り線: 「---」
4. ★YouTube動画の埋め込み★ 記事の適切な位置に「{{{{YOUTUBE_URL}}}}」プレースホルダーを単独行で入れること。
5. 動画内の出来事、特にハプニングや失敗があれば、それを「最高のオチ」として大げさにエンタメへ昇華させる。
6. 段落ごと・話題の転換ごとに空行を入れ、読みやすさを最優先にすること。
7. ★商品紹介（控えめに）★ 記事の終盤に{shop_name}の商品について触れてもよいが、さらっと一言だけ。
【参考：販売している商品一覧】
{products_text}{not_selling_text}
8. ★まとめセクション（必須）★ 記事の最後に「## 📝 まとめ」という見出しを入れ、要点を箇条書き3〜5行で簡潔にまとめること。
9. ★フォロー・スキの促進★ まとめの後に、{persona}らしい口調でフォロー・スキを促す一言を入れること。
10. ★禁止事項★ 宣伝へのメタ発言・楽屋ネタは一切入れないこと。
11. 記事内容に関連するSNS用ハッシュタグ（#付き）を5〜10個生成してください。

【出力形式】
必ず以下のJSONフォーマット（Markdownコードブロックなしの生のJSON文字列のみ）で出力し、他の文字は含めないこと。
{{
    "titles": ["タイトル案1(クリック重視)", "タイトル案2(SEO重視)", "タイトル案3(おもしろ系)"],
    "body": "Markdown記法を使ったリッチな記事本文",
    "hashtags": ["#ハッシュタグ1", "#ハッシュタグ2", "#ハッシュタグ3", "#ハッシュタグ4", "#ハッシュタグ5"]
}}
"""
    else:
        rules = f"""
【構成ルール】
1. タイトルは絶対に【{title_max}文字以内】に厳守しつつ、全くテイストの違う3パターンのタイトル案（①クリック重視の煽り系、②検索SEO重視、③SNS向けのおもしろ系）を提案してください。
2. 動画内の出来事、特にハプニングや失敗があれば、それを「最高のオチ」として大げさにエンタメへ昇華させる。
3. ★改行ルール（超重要）★ 文章がぎゅうぎゅう詰めにならないよう、段落ごと・話題の転換ごとに【必ず2〜3行の空行】を入れること。絵文字や「【】」「◆」などの全角記号を使って見やすく装飾する。（※{platform}にそのままコピペするため、Markdown記法は一切使わないこと。プレーンテキストで出力する。）
4. 画像挿入指示は不要です。テキストのみで出力してください。
5. ★重要★ {shop_name}の商品宣伝： 記事の終盤に、必ず「◆◆ {shop_name}からのお知らせ ◆◆」という見出し行を書き、その【後に】商品紹介の文を続けてください。
【実際に販売している商品一覧（これ以外の商品を捏造しないこと！）】
{products_text}{not_selling_text}
6. ★重要★ アクションの促進： 最下部で、YouTubeやBASEアプリのショップフォローを促す一言を入れてください。
7. ★禁止事項★ 宣伝へのメタ発言・楽屋ネタは一切入れないこと。
8. 記事内容に関連するハッシュタグ（#付き）を5〜10個生成してください。

【出力形式】
必ず以下のJSONフォーマット（Markdownコードブロックなしの生のJSON文字列のみ）で出力し、他の文字は含めないこと。
{{
    "titles": ["タイトル案1(クリック重視)", "タイトル案2(SEO重視)", "タイトル案3(おもしろ系)"],
    "body": "Markdownを使わない、空行をたっぷり入れたプレーンテキストの記事本文",
    "hashtags": ["#ハッシュタグ1", "#ハッシュタグ2", "#ハッシュタグ3", "#ハッシュタグ4", "#ハッシュタグ5"]
}}
"""
    return header + rules


# ========== 後処理 ==========
def postprocess_body(body: str, url: str, config: dict) -> str:
    """本文にYouTube URL挿入と空行調整を行う"""
    shop_name = config.get("shop_name", "お店")
    platform = config.get("platform", "BASE")
    base_friendly_url = normalize_youtube_url(url)

    if platform.lower() == "note":
        body = body.replace("{{YOUTUBE_URL}}", base_friendly_url)
        body = body.replace("{YOUTUBE_URL}", base_friendly_url)
        if base_friendly_url not in body:
            body += f"\n\n---\n\n🎬 元動画はこちら！\n{base_friendly_url}\n"
    else:
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
