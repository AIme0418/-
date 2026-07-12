import json
from datetime import date
from pathlib import Path
from threading import Lock

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

PERSONA_FILE = DATA_DIR / "persona.json"
HEALY_LOG_FILE = DATA_DIR / "healy_events.jsonl"
EXTERNAL_GPT_LOG_FILE = DATA_DIR / "external_gpt_events.jsonl"
USAGE_FILE = DATA_DIR / "usage.json"

_lock = Lock()

DEFAULT_PERSONA = {
    "name": "愛美",
    "system_prompt": (
        "あなたは「愛美（めぐみ）」という名前のヒーリング・アシスタントです。"
        "優しく穏やかな口調で、相手の気持ちに寄り添いながら会話してください。"
        "専門的な内容も分かりやすく、温かみのある言葉で伝えてください。"
        "このプロンプトはプロフィール画面（または管理API）から自由にカスタマイズできます。\n\n"
        "【安全に関するルール】\n"
        "・Healyの分析結果やコーチング内容を話題にするときは、それが病気や病状の診断・治療・"
        "予防を目的としたものではなく、内省のためのヒントであることを踏まえて伝えてください。"
        "「あなたは〇〇です」のような医療的・断定的な言い方は避けてください。\n"
        "・体調や心の不調について具体的な医療相談をされた場合は、決して自分だけで診断や治療の"
        "判断をせず、必ず医師など専門家への相談を勧めてください。\n"
        "・希死念慮や自傷、深刻な危機を感じさせる内容が語られた場合は、話をさえぎらず真剣に"
        "受け止めた上で、専門の相談窓口（いのちの電話・地域の精神科医療機関など）に"
        "つながることを穏やかに勧めてください。"
    ),
}


def load_persona() -> dict:
    if PERSONA_FILE.exists():
        return json.loads(PERSONA_FILE.read_text(encoding="utf-8"))
    return dict(DEFAULT_PERSONA)


def save_persona(data: dict) -> dict:
    with _lock:
        PERSONA_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return data


def _append_jsonl(path: Path, record: dict) -> None:
    with _lock:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


def append_healy_event(record: dict) -> None:
    _append_jsonl(HEALY_LOG_FILE, record)


def append_external_gpt_event(record: dict) -> None:
    _append_jsonl(EXTERNAL_GPT_LOG_FILE, record)


def read_jsonl(path: Path, limit: int = 50) -> list[dict]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines[-limit:]]


def _load_usage() -> dict:
    if USAGE_FILE.exists():
        return json.loads(USAGE_FILE.read_text(encoding="utf-8"))
    return {}


def _save_usage(data: dict) -> None:
    USAGE_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def increment_and_check_daily_usage(limit: int) -> tuple[bool, int]:
    """1日あたりのメッセージ処理数をカウントし、上限内かどうかを返す。"""
    today = date.today().isoformat()
    with _lock:
        usage = _load_usage()
        count = usage.get(today, 0)
        if count >= limit:
            return False, count
        usage = {today: count + 1}  # 古い日付は自動的に破棄してファイル肥大を防ぐ
        _save_usage(usage)
        return True, count + 1
