# Healy Backend

愛美さんの24時間対応バックエンド。LINE Messaging APIのwebhookを受け、Gemini/Claude/OpenAIのいずれかで応答を生成し、LINEに返信する。ヒーリーデータや他GPTからの入力を受け取る口も持つ。

## セットアップ

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
copy .env.example .env        # 中身を実際のキーで埋める
```

`.env` に設定する値:

- `LINE_CHANNEL_SECRET` / `LINE_CHANNEL_ACCESS_TOKEN` — LINE Developersコンソールで発行
- `GEMINI_API_KEY` / `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` — 使うものだけでOK
- `ADMIN_API_TOKEN` — persona更新やhealyデータ取得を守るトークン。長いランダム文字列に変更すること
- `DAILY_MESSAGE_LIMIT` — 1日に処理するLINEメッセージの上限（コスト暴走防止）

## ローカル起動

```bash
uvicorn main:app --reload --port 8000
```

`http://localhost:8000/` にアクセスして `{"status": "ok"}` が返れば起動成功。

## エンドポイント

| メソッド | パス | 用途 | 認証 |
|---|---|---|---|
| POST | `/webhook/line` | LINEからのメッセージを受信し自動返信 | LINE署名検証 |
| GET/PUT | `/api/persona` | 愛美さんの人格・システムプロンプトの取得/更新 | `Authorization: Bearer <ADMIN_API_TOKEN>` |
| POST/GET | `/api/healy-data` | ヒーリーデータ（汎用）の受信/一覧 | 同上 |
| POST | `/api/healy-data/coaching-report` | Healyコーチング分析レポートの受信（`client_initials`はイニシャルで保存すること） | 同上 |
| POST/GET | `/api/external-gpt` | 他GPTからの回答の受信/一覧 | 同上 |
| POST | `/api/public-chat` | フロントエンド用の公開チャット窓口（1日上限＋IPごとの簡易レート制限で保護） | なし |

## LINEとの接続手順

1. LINE Developersでチャネルを作成し、Messaging APIを有効化
2. このサーバーを公開URLでホスト（下記デプロイ参照）
3. LINE ConsoleのWebhook URLに `https://<公開URL>/webhook/line` を設定し、Webhookを有効化
4. 応答モードを「Bot」にし、LINE公式アプリの自動応答を無効化（重複防止）

## デプロイ（24時間稼働）

NetlifyはPythonの常駐サーバーを動かせないため、フロントエンド（既存index.html）はNetlifyのまま、このバックエンドは以下のような常時起動サービスに乗せる:

- Render.com / Railway.app（無料〜低価格枠あり、FastAPIをそのままデプロイ可能）
- Fly.io（Dockerfileでのデプロイ、無料枠あり）

`Dockerfile` を同梱しているので、上記のどのサービスでもそのままビルド・デプロイできる。Renderの場合は `render.yaml` を使ったBlueprintデプロイも可能（環境変数はダッシュボードで設定）。

デプロイ後、環境変数を各サービスのダッシュボードに設定し、上記のWebhook URLをそのドメインに向ける。

## ローカルでLINEなしに動作確認する

APIキーを1つだけ`.env`に設定すれば、LINEやデプロイ環境を用意しなくても以下で会話生成を試せる:

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Authorization: Bearer <ADMIN_API_TOKEN>" \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"こんにちは\"}"
```

## テスト

```bash
pip install -r requirements-dev.txt
pytest
```

署名検証・レート制限・persona保存など、外部APIキー不要な範囲を自動テストでカバーしている。

## コスト・セキュリティ

- `DAILY_MESSAGE_LIMIT` により1日の処理件数に上限を設定（超過分は定型メッセージで打ち止め）
- `/api/*` の管理系エンドポイントは `ADMIN_API_TOKEN` によるBearer認証必須
- APIキー・トークン類は `.env` にのみ保存し、`.gitignore` でリポジトリに含まれないようにしている
