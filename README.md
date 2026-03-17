# 🤖 YouTube → ブログ自動生成 LINE Bot (クラウド版)

スマホのLINEから **YouTube URL** を送るだけで、AIが自動的にブログ記事（BASE等に対応）を書いてくれるBotです。
**PC不要** で、無料のクラウドサービス（Render）にデプロイして使えます。

## ✨ 特徴
- 📱 スマホとLINEだけで完結（PCを起動しておく必要なし）
- ☁️ [Render](https://render.com/) の無料枠で24時間稼働
- 🧠 Gemini API を使って超高クオリティな記事を生成
- 🔒 設定（店名や製品情報など）は環境変数で安全に管理

---

## ⚠️ 【重要：著作権および利用に関する免責事項】
1. **本ツールは、必ず「あなた自身が権利を持つ動画」または「権利者から事前の利用許諾を得た動画」にのみ使用してください。** 他人の動画を無断でブログ記事化してご自身の商品を宣伝する行為は、著作権（翻案権等）の侵害となります。
2. 本ツールはYouTubeの動画に対応しています（TikTokやInstagramリール等は対象外です）。また外部サービスを利用した非公式な技術を使用しているため、各プラットフォームの規約変更等により予告なく使用できなくなる可能性があります。
3. Google AI Studio（無料版）に入力されたデータはGoogleのAI学習に利用される可能性があります。機密情報や個人情報の取り扱いにご注意ください。
4. **本ツールの利用によって生じたいかなる損害・トラブル・アカウント停止・著作権侵害の申し立て等についても、開発元では一切の責任を負いません。完全な自己責任にてご利用ください。**

---

## 🛠 デプロイ手順 (PC不要・ブラウザで完結)

他のユーザーが自分の専用Botを作る場合、以下の手順を行ってください。

### 1. 各種アカウントとキーの準備
以下の3つの準備が必要です。

1. **Gemini API キー**
   - [Google AI Studio](https://aistudio.google.com/app/apikey) にアクセスし、「Create API Key」からキーを作成します。
2. **LINE Bot チャンネル**
   - [LINE Developers](https://developers.line.biz/) でプロバイダーとチャネル（Messaging API）を作成します。
   - 以下の2つの情報を控えます：
     - `LINE_CHANNEL_SECRET` (チャネルシークレット)
     - `LINE_CHANNEL_ACCESS_TOKEN` (チャネルアクセストークン)
3. **GitHub と Render アカウント**
   - このリポジトリを自分の GitHub にフォーク（Fork）します。
   - [Render.com](https://render.com/) にGitHubアカウントでログインします。

### 2. Render にデプロイ
1. Renderのダッシュボードで **「New」** → **「Web Service」** をクリック。
2. **「Build and deploy from a Git repository」** を選び、フォークしたリポジトリを選択します。
3. 以下の設定が自動で読み込まれますが、もし聞かれたら設定してください。
   - **Environment**: `Python`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app --bind 0.0.0.0:$PORT --timeout 300`
   - **Plan**: `Free`
4. **Environment Variables（環境変数）** の設定に、以下を追加します:

| 項目 | 設定例 | 説明 |
|---|---|---|
| `GEMINI_API_KEY` | `AIza...` | Google AI Studio で取得したAPIキー |
| `LINE_CHANNEL_SECRET` | `xxxx` | LINE Developers のチャネルシークレット |
| `LINE_CHANNEL_ACCESS_TOKEN` | `xxxx` | LINE Developers のアクセストークン |
| `SHOP_NAME` | `あわじのきのこや` | あなたのお店の名前 |
| `PERSONA` | `奥田` | 記事を書く人の名前/役職 |
| `FIRST_PERSON` | `私` | 一人称（私、僕、俺など） |
| `TONE` | `エンタメ` | 文体（エンタメ / カジュアル / 丁寧） |
| `PRODUCTS` | `乾燥しいたけ, パウダー` | カンマ区切りで販売している商品を入力 |

※ 使わない項目（例：販売していない商品 `NOT_SELLING`）は設定しなくても動きます。

5. 一番下の **「Create Web Service」** をクリックすると、デプロイ（構築）が始まります。
6. 数分後、完了すると左上に `https://xxxxx.onrender.com` のようなURLが表示されます。これをコピーします。

### 3. LINE の Webhook 設定
1. LINE Developers の「Messaging API設定」画面を開きます。
2. **Webhook URL** に先ほどのURL + `/callback` を入力します。
   - 例: `https://xxxxx.onrender.com/callback`
3. 「Webhookの利用」を **オン** にします。
4. 「検証」ボタンを押して「成功」と表示されればOK！
5. **重要**: 「応答メッセージ」の設定をクリックし、**「応答メッセージ」をオフ** にしてください（Botが邪魔をしないようにするため）。

---

## 🚀 使い方
自身のスマホのLINEで、作成したBotを友だち追加します。
YouTube動画のURL（`https://youtu.be/...` など）をメッセージで送ると、裏側でAIが視聴し、約1〜2分で完成したブログ記事がLINEに届きます！
