"""LINEから、管理者本人だけが使える簡易コマンド。

管理者のLINEユーザーIDからのメッセージが決まったキーワードに一致したときだけ、
めぐみさんとしての会話ではなく、この管理コマンドとして処理する。
"""

import logging

from . import storage
from .routers.clients import summarize_client

logger = logging.getLogger("admin_commands")


async def handle_admin_command(user_text: str) -> str | None:
    """一致するコマンドがあれば返信文を返す。一致しなければNoneを返し、通常の会話に委ねる。"""
    text = user_text.strip()

    if text in ("クライアント一覧", "クライアント一覧を見せて"):
        return _list_clients_reply()

    if text.startswith("要約"):
        name = text[len("要約"):].strip()
        return await _summary_reply(name)

    if text in ("セキュリティ確認", "セキュリティチェック"):
        return _security_reply()

    return None


def _list_clients_reply() -> str:
    clients = storage.list_clients()
    if not clients:
        return "まだ会話履歴のあるクライアントはいません。"
    lines = [f"・{c['display_name']}（{c['message_count']}件）" for c in clients]
    return "クライアント一覧:\n" + "\n".join(lines)


async def _summary_reply(name: str) -> str:
    if not name:
        return "「要約 〇〇さん」のように、名前を指定してください。"

    clients = storage.list_clients()
    match = next((c for c in clients if name in c["display_name"]), None)
    if not match:
        return f"「{name}」に一致するクライアントが見つかりませんでした。"

    try:
        result = await summarize_client(match["client_id"])
    except Exception:
        logger.exception("Admin command summary failed")
        return "要約の生成に失敗しました。もう一度お試しください。"

    return f"{result['display_name']}さんの要約:\n{result['summary']}"


def _security_reply() -> str:
    events = storage.read_jsonl(storage.SECURITY_LOG_FILE, limit=200)
    if not events:
        return "直近の不正アクセスの記録はありません。"
    recent = events[-10:]
    lines = [f"・{e['at']}: {e['type']}" for e in recent]
    return f"直近のセキュリティイベント（全{len(events)}件中、最新{len(recent)}件）:\n" + "\n".join(lines)
