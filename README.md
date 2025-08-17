# x-post-bot

Notionの投稿キューをもとに **X（旧Twitter）** に自動ポストする最小構成のボットです。  
ローカル実行でのワンショット投稿と、**GitHub Actions + AWS Systems Manager Parameter Store**（SSM）を使った**毎朝の定期投稿**に対応します。

---

## 主な特徴

- 🗂 **Notion → X の投稿パイプライン**
  - Notionデータベースから `Status = ready` のページを1件取り出し
  - ページ内容をテキスト化してXに投稿
  - 成功したら `Status = posted` に更新し、`PostedAt` にUTC時刻を記録
- 🔐 **OAuth 2.0（PKCE）でのXユーザー認可**
  - 初回は対話式に認可URLを開き、リダイレクトURLをコピペ
  - `token.json` に保存し、以降は**自動リフレッシュ**
- ☁️ **SSM連携によるトークンの安全保管**
  - GitHub Actions 実行前に SSM から `token.json` を取得
  - 実行後にリフレッシュされた `token.json` を SSM に**自動書き戻し**
- 🕗 **定期実行**
  - 既定のスケジュールは**毎朝 8:00 JST**（GitHubはUTC運用のため `0 23 * * *`）
- ⚙️ **シンプルな構成・型依存の少ないAPI設計**
  - Tweepyのレスポンス型に依存せず `Dict` を返す薄いラッパー

---

## リポジトリ構成

```
x-post-bot/
├─ .github/workflows/post_scheduler.yml   # GitHub Actions（定期実行）
├─ .gitignore
├─ config.py                              # .env / Secrets 読み出し
├─ notion_queue.py                        # Notionキューの取得・更新
├─ oauth2_flow.py                         # X OAuth2 フロー + SSM連携
├─ post.py                                # エントリポイント（投稿処理）
├─ requirements.txt
├─ token_store.py                         # token.json の保存/読込
├─ x_api.py                               # Tweepy薄ラッパー
└─ README.md
```

> **補足**: `.env` と `token.json` は `.gitignore` 済みです。秘匿情報は **コミットしない** でください。

---

## 動作要件

- Python **3.10+**（推奨）
- X Developerアカウント（OAuth2 / user context）
- Notionインテグレーション（Token + Database）
- （定期実行する場合）GitHub Actions / AWS SSM（Parameter Store）

---

## 1) 依存関係のインストール

```bash
# 仮想環境は任意
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate

pip install -r requirements.txt
```

> もし `requirements.txt` の文字コードでエラーになる場合は UTF-8 に変換してください。中身は以下が目安です：  
> `tweepy, notion-client, python-dotenv, requests-oauthlib, httpx, boto3（Actions用）, pandas/numpy ほか`

---

## 2) 環境変数の設定（.env）

`.env` をプロジェクト直下に作成します（GitHub Actions では Secrets/Variables に設定）。

```dotenv
# X (Twitter) OAuth2
X_CLIENT_ID=xxxxx
X_CLIENT_SECRET=xxxxx
X_REDIRECT_URI=http://localhost:8000/callback   # 任意の登録済みリダイレクトURI

# Notion
NOTION_TOKEN=secret_xxxxxxxxxxxxxxxxx
NOTION_DB_ID=xxxxxxxxxxxxxxxxxxxxxxxx

# Notion プロパティ名（必要なら上書き）
NOTION_STATUS_READY=ready
NOTION_STATUS_POSTED=posted
NOTION_TITLE_PROP=Text

# AWS（Actionsで使う）
AWS_REGION=ap-northeast-1
SSM_PARAM_NAME=/x-post-bot/token.json
```

> `X_REDIRECT_URI` は X Developer Portal に**正確に登録**してください。ローカル実行では、認可後にブラウザがこのURIへリダイレクトされます。**そのURLをまるごとコピペ**してCLIに貼り付けます。

---

## 3) Notion データベースの準備

- データベースに最低限以下のプロパティが必要です：
  - **Title**: `Text`（デフォルト名。別名にしたい場合は `NOTION_TITLE_PROP` を設定）
  - **Status**: Select（値: `ready`, `posted`）
  - **PostedAt**: Date
- **権限**: 作成した Notion インテグレーションを**データベースに招待**し、読み書き権限を付与してください。

> 取り出し条件は「`Status = ready` のレコードから1件」。どのフィールドをツイートするかは `notion_queue.page_text()` で定義しています（既定はタイトルを使う想定）。

---

## 4) ローカルでの投稿テスト（初期トークン発行）

初回は対話式に OAuth2 認可を行い、`token.json` を生成します。

```bash
python post.py
# → 認可URLが表示される
# → ブラウザで認可 → リダイレクト先に飛ぶ
# → アドレスバーの「完全なURL」をCLIに貼り付け
# → token.json が作成される（次回以降は自動リフレッシュ）
```

> `401 Unauthorized` などが出る場合：  
> - Xアプリの権限に **tweet.read / tweet.write / users.read / offline.access** の4つが含まれるか確認  
> - `client_id / client_secret / redirect_uri` が正しいか確認  
> - 同じアプリで作ったトークンか（別アプリのトークンは使えません）

---

## 5) 定期投稿（GitHub Actions + AWS SSM）

### 5-1. 事前に用意するもの

- GitHub リポジトリ（このコードをプッシュ）
- **Actions 用 OIDCロール**（AWS側）
  - 信頼ポリシー: GitHub OIDC を信頼
  - アタッチ権限例: `ssm:GetParameter`, `ssm:PutParameter`
- SSM パラメータ（SecureString）
  - 名前例: `/x-post-bot/token.json`
  - 値: **ローカルで生成した `token.json` の中身**（JSON全体）を事前登録

> 初回は Actions 上で対話認可ができないため、**ローカルで発行した token.json を SSM に入れておく**のがポイントです。以降は Actions 実行で自動リフレッシュ＆SSMへ上書き保存されます。

### 5-2. GitHub 側の設定

- **Repository secrets**（Settings → Secrets and variables → Actions → Secrets）
  - `X_CLIENT_ID`
  - `X_CLIENT_SECRET`
  - `X_REDIRECT_URI`
  - `NOTION_TOKEN`
- **Repository variables**（同 → Variables）
  - `NOTION_DB_ID`
- （Workflow 内の `env` で）
  - `AWS_REGION=ap-northeast-1`
  - `SSM_PARAM_NAME=/x-post-bot/token.json`

### 5-3. ワークフロー（抜粋）

`.github/workflows/post_scheduler.yml`

```yaml
name: Post to X

on:
  schedule:
    - cron: '0 23 * * *'  # JST 8:00（GitHubはUTC）
  workflow_dispatch: {}

permissions:
  id-token: write
  contents: read

env:
  AWS_REGION: ap-northeast-1
  SSM_PARAM_NAME: /x-post-bot/token.json

jobs:
  post:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install deps
        run: pip install -r requirements.txt

      # 1) OIDC で一時的にAWS認証（事前にロールと権限を用意）
      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::<ACCOUNT_ID>:role/<ROLE_NAME>
          aws-region: ${{ env.AWS_REGION }}

      # 2) token.json を SSM から取得
      - name: Pull token.json from SSM
        run: |
          aws ssm get-parameter \
            --name "${SSM_PARAM_NAME}" \
            --with-decryption \
            --region "${AWS_REGION}" \
          | jq -r '.Parameter.Value' > token.json

      # 3) Secrets/Vars の注入と投稿実行
      - name: Run post.py
        env:
          X_CLIENT_ID: ${{ secrets.X_CLIENT_ID }}
          X_CLIENT_SECRET: ${{ secrets.X_CLIENT_SECRET }}
          X_REDIRECT_URI: ${{ secrets.X_REDIRECT_URI }}
          NOTION_TOKEN: ${{ secrets.NOTION_TOKEN }}
          NOTION_DB_ID: ${{ vars.NOTION_DB_ID }}
        run: python post.py

      # 4) リフレッシュされた token.json を SSM に書き戻し
      - name: Save refreshed token.json back to SSM
        run: |
          aws ssm put-parameter \
            --name "${SSM_PARAM_NAME}" \
            --type SecureString \
            --value file://token.json \
            --overwrite \
            --region "${AWS_REGION}"
```

---

## 実装の概念図

```
[Notion DB] --pick_ready--> (page) --page_text--> "tweet text"
                                          |
                                          v
                                       create_tweet
                                          |
                                          v
                    (ok) mark_posted(Status=posted, PostedAt=now UTC)
```

- `notion_queue.pick_ready()` : `Status=ready` の最古1件を取得（想定）  
- `notion_queue.page_text()` : 投稿本文を生成（既定はタイトル）  
- `x_api.create_text_tweet()` : Tweepyで投稿し、`{"id": "...", "data": ..., "raw": ...}` を返す  
- `notion_queue.mark_posted()` : 成功時に Notion を更新

---

## 例外・リトライの取り扱い

- **重複投稿**: X API からの 403（Duplicate）を検知し、投稿はスキップしつつ Notion 側を `posted` に更新します。
- **認可エラー**: リフレッシュ失敗時はローカルの対話実行では再認可にフォールバック。Actions では失敗で終了します（SSMのトークンを入れ替えて再実行してください）。

---

## 開発メモ

- `config.py` は `.env` → 環境変数（GitHub Secrets/Vars含む）を統一的に扱います。
- ローカル開発では `OAUTHLIB_INSECURE_TRANSPORT=1` を強制し、HTTPのリダイレクトURIでも動くようにしています（本番はHTTPS推奨）。
- 仕様変更に強いよう、外部APIの戻り型には強く依存しない薄いラッパーにしています。

---

## ライセンス

（選択して追記してください。例：MIT）

---

## よくある質問（FAQ）

**Q. Notion のどのフィールドがツイートされますか？**  
A. 既定ではタイトル（`NOTION_TITLE_PROP`）です。本文や別フィールドを使いたい場合は `notion_queue.page_text()` をカスタマイズしてください。

**Q. 初回の GitHub Actions 実行で失敗します。**  
A. 対話認可ができないため、**先にローカルで token.json を作って SSM に入れておく**必要があります。

**Q. Cronの時刻は日本時間ですか？**  
A. GitHub Actions の `cron` は **UTC** で解釈されます。サンプルは `0 23 * * *`（**JST 8:00** 相当）です。

**Q. 文字数や改行の扱いは？**  
A. Xの上限規定に入りきらない場合はエラーになります。`page_text()` でトリミングや整形ルールを実装してください。

---

## 保守・拡張のヒント

- 画像投稿/引用投稿などは `x_api.py` に関数を追加して拡張
- 複数件ポストやスレッド投稿は `post.py` にループ/分岐を追加
- Notion 側のキュー制御（優先度／予約日時）を入れたい場合は、クエリ条件やソート条件を `notion_queue.py` に追加

---

Happy posting! 🕊️
