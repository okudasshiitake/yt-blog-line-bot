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


# ========== 動画ダウンロード（PC版 / フォールバック用） ==========
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


# ========== YouTube字幕（トランスクリプト）取得 ==========
def extract_video_id(url: str) -> str:
    """URLからYouTubeの動画IDを抽出する"""
    m = re.search(r"(?:v=|/shorts/|youtu\.be/)([^&?]+)", url)
    if m:
        return m.group(1)
    raise ValueError(f"YouTube動画IDを抽出できませんでした: {url}")


def get_transcript(url: str) -> str:
    """YouTubeの字幕（トランスクリプト）をテキストとして取得する"""
    from youtube_transcript_api import YouTubeTranscriptApi

    video_id = extract_video_id(url)
    ytt = YouTubeTranscriptApi()

    # 日本語 → 英語の順で試行
    for langs in [["ja"], ["en"], ["ja", "en"]]:
        try:
            transcript = ytt.fetch(video_id, languages=langs)
            text_parts = [snippet.text for snippet in transcript]
            return "\n".join(text_parts)
        except Exception:
            continue

    # 言語指定なしで最終トライ
    try:
        transcript = ytt.fetch(video_id)
        text_parts = [snippet.text for snippet in transcript]
        return "\n".join(text_parts)
    except Exception:
        raise RuntimeError(
            "この動画には字幕（自動生成含む）がありません。\n"
            "字幕のある動画でお試しください。"
        )


def get_video_title(url: str) -> str:
    """yt-dlpを使ってYouTube動画のタイトルを取得する（ダウンロードなし）"""
    try:
        ydl_opts = {"quiet": True, "no_warnings": True, "skip_download": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get("title", "")
    except Exception:
        return ""


# ========== AI記事生成 ==========
def generate_article_from_transcript(transcript: str, url: str, config: dict, user_instruction: str = "") -> dict:
    """字幕テキストをGemini AIに渡し、ブログ記事を生成する"""
    system_instruction = build_system_prompt(config, user_instruction)
    model_name = config.get("model", "gemini-2.0-flash")
    temperature = config.get("temperature", 0.8)

    # 動画タイトルも取得できれば参考情報として渡す
    video_title = get_video_title(url)
    title_hint = f"\n動画タイトル: 「{video_title}」" if video_title else ""

    model = genai.GenerativeModel(
        model_name=model_name,
        system_instruction=system_instruction,
        generation_config={
            "response_mime_type": "application/json",
            "temperature": temperature,
        },
    )

    prompt = (
        f"以下はYouTube動画の字幕テキスト（話した内容の書き起こし）です。{title_hint}\n"
        f"この内容を元に、指示通りのJSONフォーマットでブログ記事を出力してください。\n\n"
        f"【字幕テキスト】\n{transcript[:15000]}"
    )

    response = model.generate_content(prompt)

    try:
        data = json.loads(response.text)
        if isinstance(data, list) and len(data) > 0:
            data = data[0]
        return data
    except json.JSONDecodeError:
        raise RuntimeError(f"AIの出力がJSON形式ではありませんでした: {response.text[:200]}")


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

    # --- 共通ヘッダー ---
    header = f"""
【あなたの役割（ペルソナ）】
あなたは「{shop_name}」の『{persona}本人』です。ブログの語り手として、一人称「{first_person}」を使用し、ユーモア溢れる親しみやすいトーンで語りかけてください。
※ただし、文章の執筆スキルは{tone_desc}を持って執筆してください。（※作中で自分がライターや編集長であると自称・名乗る必要は一切ありません。あくまで{persona}として振る舞ってください。）
アップロードされた動画の内容を元に、最高に面白くて読者の目を惹く{platform}用の記事を作成してください。
{custom_rules_section}{user_instruction_section}"""

    # --- プラットフォーム別の構成ルール ---
    if platform.lower() == "note":
        rules = f"""
【構成ルール（note特化版）】
1. タイトルは絶対に【{title_max}文字以内】に厳守しつつ、全くテイストの違う3パターンのタイトル案（①クリック重視の煽り系、②Google検索SEO重視、③SNS向けのおもしろ系）を提案してください。
2. ★冒頭のつかみ（超重要）★ noteではタイムラインや検索結果で最初の数行のみ表示される。記事の冒頭1〜2文で「え、なにそれ？」「続きが気になる！」と思わせる強烈なフックを必ず入れること。
3. ★リッチテキスト★ noteはMarkdownに近いリッチテキストに対応しています。以下を積極的に使って、noteの画面上で映える「読みたくなるデザイン」に仕上げてください：
   - 見出し: 「## 見出し」（##を使用。#は記事タイトル用なので本文では##以降を使う）
   - 太字: 「**強調したい言葉**」
   - 引用: 「> 引用文」（印象的なセリフや名言を引用ブロックで目立たせる）
   - 箇条書き: 「- 項目」
   - 区切り線: 「---」（話題の転換に使用）
4. ★YouTube動画の埋め込み★ noteではYouTubeのURLを本文中に単独行で記載すると、自動的に動画プレーヤーが埋め込み表示される。記事の適切な位置（冒頭の導入後など）に、YouTube URLだけの行を1つ入れること。URLは「{{YOUTUBE_URL}}」というプレースホルダーで記載すること。
5. 動画内の出来事、特にハプニングや失敗があれば、それを「最高のオチ」として大げさにエンタメへ昇華させる。
6. 段落ごと・話題の転換ごとに空行を入れ、読みやすさを最優先にすること。
7. ★商品紹介（控えめに）★ 記事の終盤に{shop_name}の商品について触れてもよいが、noteの読者はあからさまな宣伝を嫌う。「ちなみに、こんなのもやってます」程度の自然さで、さらっと一言だけ触れる形にすること。直接的な「買ってください」は禁止。
【参考：販売している商品一覧】
{products_text}{not_selling_text}
8. ★まとめセクション（必須）★ 記事の最後に「## 📝 まとめ」という見出しを入れ、この記事の要点を箇条書き3〜5行で簡潔にまとめること。noteの読者は「学び・気づき」を求めている。
9. ★フォロー・スキの促進★ まとめの後に、「この記事が面白かったら『スキ♡』とフォローをお願いします！」「YouTubeチャンネルも見てね！」のような行動を促す一言を{persona}らしい口調で入れること。
10. ★禁止事項★ 記事本文中に宣伝をしていることへのメタ発言・心の声・楽屋ネタは一切入れないこと。
11. 記事内容に関連するSNS用のハッシュタグ（#付き）を5〜10個生成してください。

【出力形式】
必ず以下のJSONフォーマット（Markdownコードブロックなしの生のJSON文字列のみ）で出力し、他の文字は含めないこと。
{{
    "titles": ["タイトル案1(クリック重視)", "タイトル案2(SEO重視)", "タイトル案3(おもしろ系)"],
    "body": "Markdown記法（##見出し・**太字**・>引用・-箇条書き）を使ったリッチな記事本文",
    "hashtags": ["#ハッシュタグ1", "#ハッシュタグ2", "#ハッシュタグ3", "#ハッシュタグ4", "#ハッシュタグ5"]
}}
"""
    else:
        # --- BASE / その他のプラットフォーム ---
        rules = f"""
【構成ルール】
1. タイトルは絶対に【{title_max}文字以内】に厳守しつつ、全くテイストの違う3パターンのタイトル案（①クリック重視の煽り系、②検索SEO重視、③SNS向けのおもしろ系）を提案してください。
2. 動画内の出来事、特にハプニングや失敗があれば、それを「最高のオチ」として大げさにエンタメへ昇華させる。
3. ★改行ルール（超重要）★ 文章がぎゅうぎゅう詰めにならないよう、段落ごと・話題の転換ごとに【必ず2〜3行の空行】を入れること。1文ごとに改行しても構わないくらい、たっぷりスペースを使って読みやすくすること。絵文字や「【】」「◆」などの全角記号を使って見やすく装飾する。（※{platform}にそのままコピペするため、アスタリスク「**」やシャープ「#」などのMarkdown記法は一切使わないこと。プレーンテキストで出力する。）
4. 画像挿入指示は不要です。テキストのみで出力してください。
5. ★重要★ {shop_name}の商品宣伝： 記事の終盤に、必ず「◆◆ {shop_name}からのお知らせ ◆◆」という見出し行を書き、その【後に】商品紹介の文を続けてください。見出しの前に商品紹介を書き始めないこと。動画内容に自然に絡めて、{persona}らしいおどけた感じで紹介してください。
【実際に販売している商品一覧（これ以外の商品を捏造しないこと！）】
{products_text}{not_selling_text}
6. ★重要★ アクションの促進： 最下部で、次回の動画やブログ実験の期待を煽り、YouTubeやBASEアプリのショップフォローを促す一言を入れてください。
7. ★禁止事項★ 記事本文中に「（宣伝も忘れない）」「（ここで宣伝です）」「（さりげなく宣伝）」のような、宣伝をしていることへのメタ発言・心の声・楽屋ネタは一切入れないこと。宣伝はあくまで自然に、読者に語りかける形でさらっと行う。
8. 記事内容や商品に関連するInstagramやTikTokで使えるおすすめのハッシュタグ（#付き）を5〜10個生成してください。

【出力形式】
必ず以下のJSONフォーマット（Markdownコードブロックなしの生のJSON文字列のみ）で出力し、他の文字は含めないこと。
{{
    "titles": ["タイトル案1(クリック重視)", "タイトル案2(SEO重視)", "タイトル案3(おもしろ系)"],
    "body": "Markdownを使わない、空行をたっぷり入れたプレーンテキストの記事本文",
    "hashtags": ["#ハッシュタグ1", "#ハッシュタグ2", "#ハッシュタグ3", "#ハッシュタグ4", "#ハッシュタグ5"]
}}
"""
    return header + rules


def generate_article(video_path: str, config: dict, user_instruction: str = "") -> dict:
    """動画をGemini AIに渡し、ブログ記事を生成する"""
    video_file = genai.upload_file(path=video_path)

    while video_file.state.name == "PROCESSING":
        time.sleep(5)
        video_file = genai.get_file(video_file.name)

    if video_file.state.name == "FAILED":
        raise RuntimeError("動画の処理に失敗しました。")

    system_instruction = build_system_prompt(config, user_instruction)
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
    platform = config.get("platform", "BASE")
    base_friendly_url = normalize_youtube_url(url)

    if platform.lower() == "note":
        # --- note モード ---
        # AIが出力した {{YOUTUBE_URL}} プレースホルダーを実際のURLに置換
        body = body.replace("{{YOUTUBE_URL}}", base_friendly_url)
        body = body.replace("{YOUTUBE_URL}", base_friendly_url)
        # もしプレースホルダーがなかった場合、末尾に追加
        if base_friendly_url not in body:
            body += f"\n\n---\n\n🎬 元動画はこちら！\n{base_friendly_url}\n"
    else:
        # --- BASE / その他 ---
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
