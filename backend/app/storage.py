import json
from datetime import date, datetime, timezone
from pathlib import Path
from threading import Lock

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

PERSONA_FILE = DATA_DIR / "persona.json"
HEALY_LOG_FILE = DATA_DIR / "healy_events.jsonl"
EXTERNAL_GPT_LOG_FILE = DATA_DIR / "external_gpt_events.jsonl"
USAGE_FILE = DATA_DIR / "usage.json"
ACTIVE_HEALY_SUMMARY_FILE = DATA_DIR / "active_healy_summary.json"
SECURITY_LOG_FILE = DATA_DIR / "security_events.jsonl"
CLIENT_LOG_FILE = DATA_DIR / "client_conversations.jsonl"
CLIENT_LINK_FILE = DATA_DIR / "client_links.json"
CLIENT_ANALYSIS_FILE = DATA_DIR / "client_analyses.json"

_lock = Lock()

DEFAULT_PERSONA = {
    "name": "愛美",
    "system_prompt": (
        "あなたは「愛美（めぐみ）」という名前の、相手に寄り添う優しいヒーラーです。\n\n"
        "【話し方】\n"
        "・丁寧な言葉遣いで話してください。ただし断定的な言い方は避け、"
        "「〜かもしれませんね」「〜のように思います」など、やわらかい語尾を使ってください。\n"
        "・相手のことは、LINEの表示名に「さん」をつけて呼んでください。\n\n"
        "【接し方】\n"
        "・相手の話には「そうなんですね」と、まず寄り添って耳を傾けてください。相手の気持ちや"
        "考えを否定せず、マイナスな言葉で声をかけることは絶対にしないでください。\n"
        "・基本的には共感し、肯定する姿勢で接してください。共感できる部分があれば、"
        "あなた自身の気持ちとして共感を伝え、優しく接してください。\n"
        "・相手を励ますときは、「無理しなくていいですよ」と、まず今の状態をそのまま"
        "受け止める言い方をしてください。\n"
        "・終始おだやかなトーンを保ち、口調が大きく変わることのないようにしてください。\n"
        "・「自分のペースでいいですよ」という言葉を、自然な場面でよく使ってください。\n"
        "・相手がマイナスな発言（自分を責める言葉、弱音、不安など）をしたときは、まず"
        "その気持ちをそのまま受け止めて共感してください。その上で、否定したり急に話題を"
        "変えたりせず、その出来事や気持ちの中にある前向きな側面・成長のきっかけ・見方を、"
        "押しつけがましくならない範囲でそっと添えてください。「でも」で気持ちを打ち消す"
        "のではなく、「そう感じるくらい頑張ってきたんですね」のように、マイナスの中にある"
        "意味を一緒に見つけるイメージで伝えてください。\n"
        "・共感し、前向きな視点を添えた後、もし力になれそうなことがあれば、ちょっとした"
        "アイデアや工夫を「もしよかったら、〇〇してみるのもいいかもしれませんね」のように、"
        "提案の形でそっと添えてください。「〇〇すべきです」のような言い切りは避け、"
        "相手が今はいらないと感じていそうなときは、無理に勧めないでください。\n\n"
        "【大切にしている価値観】\n"
        "・自分を大切にすること、自分に素直に生きることを何よりも大切に考えています。"
        "会話の中でも、この価値観がにじむようにしてください。\n\n"
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


def log_security_event(event_type: str, detail: str = "") -> None:
    """不正アクセスの試み・制限超過などを記録する（管理APIから確認できる）。"""
    _append_jsonl(
        SECURITY_LOG_FILE,
        {
            "at": datetime.now(timezone.utc).isoformat(),
            "type": event_type,
            "detail": detail,
        },
    )


def read_jsonl(path: Path, limit: int = 50) -> list[dict]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines[-limit:]]


def append_client_message(client_id: str, display_name: str, message: str) -> None:
    """LINEから届いたメッセージの原文を、あとで振り返れるように保存する。"""
    _append_jsonl(
        CLIENT_LOG_FILE,
        {
            "at": datetime.now(timezone.utc).isoformat(),
            "client_id": client_id,
            "display_name": display_name,
            "message": message,
        },
    )


def list_clients() -> list[dict]:
    """クライアントごとの最新の表示名とメッセージ件数を一覧にする。"""
    clients: dict[str, dict] = {}
    for record in read_jsonl(CLIENT_LOG_FILE, limit=10_000):
        client_id = record["client_id"]
        entry = clients.setdefault(
            client_id,
            {"client_id": client_id, "display_name": record["display_name"], "message_count": 0},
        )
        entry["display_name"] = record["display_name"]
        entry["message_count"] += 1
        entry["last_message_at"] = record["at"]
    return list(clients.values())


def get_client_messages(client_id: str, limit: int = 200) -> list[dict]:
    all_records = read_jsonl(CLIENT_LOG_FILE, limit=10_000)
    matching = [r for r in all_records if r["client_id"] == client_id]
    return matching[-limit:]


def _load_usage() -> dict:
    if USAGE_FILE.exists():
        return json.loads(USAGE_FILE.read_text(encoding="utf-8"))
    return {}


def _save_usage(data: dict) -> None:
    USAGE_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def save_active_healy_summary(client_initials: str, summary: str) -> None:
    """直近のHealyコーチング分析の要約を1件だけ保持する（家族内テスト規模向けの簡易実装）。"""
    with _lock:
        ACTIVE_HEALY_SUMMARY_FILE.write_text(
            json.dumps(
                {"client_initials": client_initials, "summary": summary},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


def load_active_healy_summary() -> dict | None:
    if not ACTIVE_HEALY_SUMMARY_FILE.exists():
        return None
    return json.loads(ACTIVE_HEALY_SUMMARY_FILE.read_text(encoding="utf-8"))


def load_client_links() -> dict:
    if CLIENT_LINK_FILE.exists():
        return json.loads(CLIENT_LINK_FILE.read_text(encoding="utf-8"))
    return {}


def save_client_link(client_initials: str, client_id: str, display_name: str = "") -> None:
    """Healyレポートのイニシャルと、LINEのclient_idを紐づけて記憶する。"""
    with _lock:
        links = load_client_links()
        links[client_initials] = {
            "client_id": client_id,
            "display_name": display_name,
            "linked_at": datetime.now(timezone.utc).isoformat(),
        }
        CLIENT_LINK_FILE.write_text(json.dumps(links, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_client_id_by_initials(client_initials: str) -> str | None:
    link = load_client_links().get(client_initials)
    return link["client_id"] if link else None


def resolve_client_id_by_display_name(display_name: str) -> str | None:
    for client in list_clients():
        if client["display_name"] == display_name:
            return client["client_id"]
    return None


def load_client_analyses() -> dict:
    if CLIENT_ANALYSIS_FILE.exists():
        return json.loads(CLIENT_ANALYSIS_FILE.read_text(encoding="utf-8"))
    return {}


def save_client_analysis(client_id: str, client_initials: str, analysis: str) -> None:
    """会話履歴とHealy分析を突き合わせた「深い気づき」を、クライアントごとに1件保持する。"""
    with _lock:
        analyses = load_client_analyses()
        analyses[client_id] = {
            "client_initials": client_initials,
            "analysis": analysis,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        CLIENT_ANALYSIS_FILE.write_text(
            json.dumps(analyses, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def load_client_analysis(client_id: str) -> dict | None:
    return load_client_analyses().get(client_id)


def build_system_prompt_with_context(client_id: str | None = None) -> str:
    """persona設定に、あれば直近のHealy要約と、この人向けの深い気づきを添えて返す。"""
    prompt = load_persona()["system_prompt"]
    summary = load_active_healy_summary()
    if summary:
        prompt += (
            f"\n\n【参考情報】このかた（{summary['client_initials']}）の直近のHealyコーチング分析"
            f"の要約: {summary['summary']}\n"
            "この内容を踏まえつつ、断定せず自然に会話に活かしてください。"
        )
    if client_id:
        analysis = load_client_analysis(client_id)
        if analysis:
            prompt += (
                f"\n\n【参考情報（深い気づき）】このかた（{analysis['client_initials']}）について、"
                "Healyの分析データとこれまでの会話から見えてきた気づき: "
                f"{analysis['analysis']}\n"
                "これは押しつけるものではないので、会話の流れの中で自然に触れられそうな"
                "ときだけそっと活かしてください。毎回触れる必要はありません。"
            )
    return prompt


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
