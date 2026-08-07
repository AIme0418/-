import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .. import storage
from ..auth import require_admin_token
from ..llm_clients import generate_reply
from ..storage import (
    append_external_gpt_event,
    append_healy_event,
    read_jsonl,
    save_active_healy_summary,
)

logger = logging.getLogger("healy")
router = APIRouter(dependencies=[Depends(require_admin_token)])

SUMMARY_SYSTEM_PROMPT = (
    "あなたはHealyのコーチング分析結果を、AIチャットボットが会話の中で自然に参照できるよう"
    "要約するアシスタントです。医療的な診断・断定表現は避け、内省のためのヒントとして"
    "2〜3文程度の日本語で簡潔にまとめてください。"
)

ANALYSIS_SYSTEM_PROMPT = (
    "あなたはHealyのコーチング分析結果と、そのクライアントとの会話の記録を"
    "つなぎ合わせて、その人固有の気づきを見出す分析アシスタントです。\n\n"
    "【目的】\n"
    "・Healyの分析データ（主患部・焦点項目・一致度・目標とする状態）は、"
    "その人の内面にある「今向き合っているテーマ」を数値化したものです。\n"
    "・そのテーマが、実際の会話の中でどんな形で表れているか（似た言葉、"
    "繰り返し出てくる悩み、避けている話題など）を探し、両者をつなげて"
    "説明してください。会話の中に直接の裏付けが見つからない項目については、"
    "無理にこじつけず、「まだ会話には表れていないテーマ」として扱ってください。\n\n"
    "【出力の考え方】\n"
    "・一致度(%)や内部コードなど、数値やコード自体をそのまま出力しないでください。"
    "それらは『どのテーマを優先して扱うか』の手がかりとしてのみ使い、"
    "説明文の中では自然な言葉に置き換えてください。\n"
    "・「〇〇という傾向がある」「〇〇な状態です」のような断定は避け、"
    "「〇〇のように感じているのかもしれません」「〇〇と向き合っている時期なのかも"
    "しれませんね」など、含みを持たせた表現にしてください。\n"
    "・目標とする状態（アファメーション文）は、ゴールの押しつけにならないよう、"
    "「そこに近づいていくヒントとして」という位置づけで触れてください。\n"
    "・そのアファメーション自体を言い換えるときは、Healy本家のプログラムで使われて"
    "いるような、一人称・現在形で、自然や身体感覚の比喩を使った、短く詩的な言葉を"
    "意識してください（例：「私のエネルギーは自由に流れている」「私は根を張り、"
    "強い木のように育っていく」）。説明的な長い文にせず、その言葉自体は言い切りの"
    "形で構いません（断定を避けるのは、気づきを説明する地の文の側だけで十分です）。\n"
    "・出力は2〜4文程度。会話の中で自然に参照できる、要約された気づきの形に"
    "してください（レポート形式の箇条書きにはしないでください）。\n\n"
    "【安全に関するルール】\n"
    "・医療的な診断・治療・予防を目的とした内容は一切含めないでください。\n"
    "・実在の人物名はイニシャルでのみ扱い、フルネームや会話中の他人の"
    "実名が含まれていても、それらを出力に含めないでください。"
)


def _build_summary_prompt(report: "HealyCoachingReport") -> str:
    lines = []
    if report.main_focus:
        lines.append(f"主患部: {report.main_focus}")
    for item in report.items:
        lines.append(
            f"・{item.category}（一致度{item.match_percent}%）: {item.target_state}"
        )
    return "\n".join(lines)


def _build_analysis_prompt(report: "HealyCoachingReport", recent_messages: list[str]) -> str:
    lines = [f"クライアント: {report.client_initials}さん"]
    if report.main_focus:
        lines.append(f"主患部: {report.main_focus}")
    lines.append("焦点項目:")
    for item in report.items:
        lines.append(
            f"・{item.category}（一致度{item.match_percent}%, 目標: {item.target_state}）"
        )
    lines.append("\n直近の会話（本人の発言のみ抜粋）:")
    for msg in recent_messages:
        lines.append(f"・{msg}")
    return "\n".join(lines)


AURA_SUMMARY_SYSTEM_PROMPT = (
    "あなたはHealyのオーラ分析結果を、AIチャットボットが会話の中で自然に参照できるよう"
    "要約するアシスタントです。\n"
    "・オーラ分析には「現在の状態」として、今その人が抱えているかもしれない制限的な"
    "思い込みが書かれていますが、これをそのまま『あなたは〇〇です』と断定的に伝え"
    "返さないでください。あくまで一つの可能性・傾向として、控えめに触れる程度に"
    "とどめてください。\n"
    "・特に家族関係や見捨てられ不安など、深く心理的な内容が含まれる場合は、具体的な"
    "描写を避け、抽象度を上げた包み込む表現にとどめてください。\n"
    "・「目標とする状態」（アファメーション）の方向性を中心に、前向きな内省のヒント"
    "として2〜3文程度の日本語で簡潔にまとめてください。\n"
    "・医療的な診断・断定表現は避けてください。"
)

AURA_ANALYSIS_SYSTEM_PROMPT = (
    "あなたはHealyのオーラ分析結果と、そのクライアントとの会話の記録をつなぎ合わせて、"
    "その人固有の気づきを見出す分析アシスタントです。\n\n"
    "【目的】\n"
    "・オーラ分析データ（チャクラごとのエネルギー・現在の状態・目標とする状態）は、"
    "その人の内面にある「今向き合っているテーマ」を表したものです。\n"
    "・「現在の状態」に書かれている制限的な思い込みが、実際の会話の中でどんな形で"
    "表れているかを探し、両者をつなげて説明してください。会話に裏付けが見つからない"
    "場合は無理にこじつけないでください。\n\n"
    "【現在の状態の扱い方（重要）】\n"
    "・「現在の状態」の文言をそのまま引用したり、断定的に言い換えたりしないでください。"
    "「〇〇と感じる瞬間があるのかもしれませんね」のように、あくまで一つの可能性として、"
    "控えめに触れてください。\n"
    "・特に家族関係・見捨てられ不安・恐怖など、深く心理的な内容が含まれる場合は、"
    "具体的な描写を避け、「大切にしたいテーマがあるようですね」のように抽象度を上げて"
    "包み込む表現にとどめてください。それを深掘りするかどうかは、あくまで本人のペース"
    "に委ねてください。\n"
    "・説明の重心は「現在の状態」ではなく「目標とする状態」（アファメーション）の"
    "方向性に置いてください。\n\n"
    "【出力の考え方】\n"
    "・一致度(%)や内部コード、エネルギー(%)の数値をそのまま出力しないでください。"
    "それらは『どのテーマを優先して扱うか』の手がかりとしてのみ使ってください。\n"
    "・アファメーション自体を言い換えるときは、Healy本家のプログラムで使われている"
    "ような、一人称・現在形で、自然や身体感覚の比喩を使った、短く詩的な言葉を"
    "意識してください。\n"
    "・出力は2〜4文程度。会話の中で自然に参照できる、要約された気づきの形にして"
    "ください（レポート形式の箇条書きにはしないでください）。\n\n"
    "【安全に関するルール】\n"
    "・医療的な診断・治療・予防を目的とした内容は一切含めないでください。\n"
    "・実在の人物名はイニシャルでのみ扱い、フルネームや会話中の他人の"
    "実名が含まれていても、それらを出力に含めないでください。"
)


def _build_aura_summary_prompt(report: "HealyAuraReport") -> str:
    lines = []
    if report.main_focus:
        lines.append(f"主患部: {report.main_focus}")
    for energy in report.chakra_energies:
        level = f"（{energy.level}）" if energy.level else ""
        lines.append(f"・{energy.chakra}: エネルギー{energy.energy_percent}%{level}")
    for item in report.items:
        lines.append(
            f"・{item.chakra}（一致度{item.match_percent}%）: "
            f"現在の状態「{item.current_state}」→ 目標とする状態「{item.target_state}」"
        )
    return "\n".join(lines)


def _build_aura_analysis_prompt(report: "HealyAuraReport", recent_messages: list[str]) -> str:
    lines = [f"クライアント: {report.client_initials}さん"]
    if report.main_focus:
        lines.append(f"主患部: {report.main_focus}")
    lines.append("焦点項目:")
    for item in report.items:
        lines.append(
            f"・{item.chakra}（一致度{item.match_percent}%）: "
            f"現在の状態「{item.current_state}」→ 目標とする状態「{item.target_state}」"
        )
    lines.append("\n直近の会話（本人の発言のみ抜粋）:")
    for msg in recent_messages:
        lines.append(f"・{msg}")
    return "\n".join(lines)


RESONANCE_SUMMARY_SYSTEM_PROMPT = (
    "あなたはHealyのレゾナンス分析結果を、AIチャットボットが会話の中で自然に参照できる"
    "よう要約するアシスタントです。\n"
    "・レゾナンス分析には、身体の部位や症状に関連する名称と一致度(%)が並んでいますが、"
    "これは身体的な健康状態の評価や診断では絶対にありません。「〇〇の調子が悪い」"
    "「〇〇に問題がある」のような、体の状態を評価する表現は一切使わないでください。\n"
    "・身体部位や症状の名称そのものを会話に出さず、「今、内面で意識が向きやすいテーマが"
    "あるようですね」のように、名称を出さずに抽象化して伝えてください。\n"
    "・数値(%)自体は出力しないでください。\n"
    "・医療的な診断・断定表現は避け、内省のためのヒントとして2〜3文程度の日本語で"
    "簡潔にまとめてください。"
)

RESONANCE_ANALYSIS_SYSTEM_PROMPT = (
    "あなたはHealyのレゾナンス分析結果と、そのクライアントとの会話の記録をつなぎ合わせて、"
    "その人固有の気づきを見出す分析アシスタントです。\n\n"
    "【目的】\n"
    "・レゾナンス分析データ（身体の部位や症状に関連する名称と一致度）は、今その人の"
    "内面で意識が向きやすいテーマの手がかりです。\n"
    "・そのテーマが、実際の会話の中でどんな形で表れているかを探し、両者をつなげて"
    "説明してください。会話に裏付けが見つからない場合は無理にこじつけないでください。\n\n"
    "【身体部位・症状名の扱い方（重要）】\n"
    "・身体の部位名・症状名を、そのまま会話に出さないでください。これは身体的な健康"
    "状態の評価や診断ではありません。「〇〇の調子が悪い」「〇〇に問題がある」のような"
    "表現は絶対に使わないでください。\n"
    "・名称は出さずに、「今、意識が向きやすいテーマ」として抽象化して伝えてください。\n\n"
    "【出力の考え方】\n"
    "・一致度(%)の数値をそのまま出力しないでください。\n"
    "・出力は2〜3文程度。会話の中で自然に参照できる、要約された気づきの形にして"
    "ください。\n\n"
    "【安全に関するルール】\n"
    "・医療的な診断・治療・予防を目的とした内容は一切含めないでください。\n"
    "・実在の人物名はイニシャルでのみ扱ってください。"
)


def _build_resonance_summary_prompt(report: "HealyResonanceReport") -> str:
    lines = []
    if report.main_focus:
        lines.append(f"主患部: {report.main_focus}")
    for item in report.items:
        lines.append(f"・{item.topic}（一致度{item.match_percent}%）")
    return "\n".join(lines)


def _build_resonance_analysis_prompt(
    report: "HealyResonanceReport", recent_messages: list[str]
) -> str:
    lines = [f"クライアント: {report.client_initials}さん"]
    if report.main_focus:
        lines.append(f"主患部: {report.main_focus}")
    lines.append("レゾナンス項目:")
    for item in report.items:
        lines.append(f"・{item.topic}（一致度{item.match_percent}%）")
    lines.append("\n直近の会話（本人の発言のみ抜粋）:")
    for msg in recent_messages:
        lines.append(f"・{msg}")
    return "\n".join(lines)


MERIDIAN_SUMMARY_SYSTEM_PROMPT = (
    "あなたはHealyの経絡分析結果を、AIチャットボットが会話の中で自然に参照できるよう"
    "要約するアシスタントです。\n"
    "・経絡分析には、臓器や経絡の名称（肝臓・膀胱・腎臓など）に紐づいた活動性・干渉性の"
    "数値が含まれますが、これは身体的な健康状態の評価や診断では絶対にありません。"
    "「〇〇の調子が悪い」「〇〇に問題がある」のような、臓器や体の状態を評価する表現は"
    "一切使わないでください。\n"
    "・臓器名や経絡名そのものを会話に出さず、そこに紐づく『目標とする状態』（アファ"
    "メーションや心のテーマ）の方向性だけを、抽象化して伝えてください。\n"
    "・数値(%)自体は出力しないでください。\n"
    "・医療的な診断・断定表現は避け、内省のためのヒントとして2〜3文程度の日本語で"
    "簡潔にまとめてください。"
)

MERIDIAN_ANALYSIS_SYSTEM_PROMPT = (
    "あなたはHealyの経絡分析結果と、そのクライアントとの会話の記録をつなぎ合わせて、"
    "その人固有の気づきを見出す分析アシスタントです。\n\n"
    "【目的】\n"
    "・経絡分析データ（経絡ごとの活動性・ツボごとの現在の課題・目標とする状態）は、"
    "その人の内面にある「今向き合っているテーマ」を表したものです。\n"
    "・ツボごとに書かれている課題が、実際の会話の中でどんな形で表れているかを探し、"
    "両者をつなげて説明してください。会話に裏付けが見つからない場合は無理にこじつけ"
    "ないでください。\n\n"
    "【臓器名・身体部位の扱い方（重要）】\n"
    "・臓器名や経絡名（肝臓・膀胱・腎臓・三焦経など）を、そのまま会話に出さないで"
    "ください。これは身体的な健康状態の評価や診断ではありません。「〇〇の調子が悪い」"
    "「〇〇に問題がある」のような表現は絶対に使わないでください。\n"
    "・課題の文言をそのまま引用せず、「〇〇と感じる瞬間があるのかもしれませんね」の"
    "ように、あくまで一つの可能性として、控えめに触れてください。\n\n"
    "【出力の考え方】\n"
    "・一致度(%)や内部コード、活動性の数値をそのまま出力しないでください。\n"
    "・アファメーションを言い換えるときは、一人称・現在形で、自然や身体感覚の比喩を"
    "使った、短く詩的な言葉を意識してください。\n"
    "・出力は2〜4文程度。会話の中で自然に参照できる、要約された気づきの形にして"
    "ください。\n\n"
    "【安全に関するルール】\n"
    "・医療的な診断・治療・予防を目的とした内容は一切含めないでください。\n"
    "・実在の人物名はイニシャルでのみ扱ってください。"
)


def _build_meridian_summary_prompt(report: "HealyMeridianReport") -> str:
    lines = []
    if report.main_focus:
        lines.append(f"主患部: {report.main_focus}")
    for item in report.items:
        notes = " / ".join(item.current_state_notes)
        lines.append(
            f"・{item.point_name}（一致度{item.match_percent}%）: "
            f"課題「{notes}」→ 目標「{item.target_state}」"
        )
    return "\n".join(lines)


def _build_meridian_analysis_prompt(
    report: "HealyMeridianReport", recent_messages: list[str]
) -> str:
    lines = [f"クライアント: {report.client_initials}さん"]
    if report.main_focus:
        lines.append(f"主患部: {report.main_focus}")
    lines.append("経絡・ツボ項目:")
    for item in report.items:
        notes = " / ".join(item.current_state_notes)
        lines.append(
            f"・{item.point_name}（一致度{item.match_percent}%）: "
            f"課題「{notes}」→ 目標「{item.target_state}」"
        )
    lines.append("\n直近の会話（本人の発言のみ抜粋）:")
    for msg in recent_messages:
        lines.append(f"・{msg}")
    return "\n".join(lines)


class HealyEvent(BaseModel):
    source: str  # 例: "healy_device", "healy_app"
    data: dict[str, Any]


class HealyCoachingItem(BaseModel):
    category: str  # 例: "焦点を特定する", "職業", "個人的責任"
    match_percent: float
    session_count: int | None = None
    code: str | None = None  # Healyアプリ内の内部コード（例: "D 1E12"）
    target_state: str  # 「目標とする状態」のアファメーション文


class HealyCoachingReport(BaseModel):
    # 個人情報保護のため、フルネームではなくイニシャルで保存する運用とする
    client_initials: str
    report_datetime: str
    main_focus: str | None = None  # 「主患部」のアファメーション文
    items: list[HealyCoachingItem] = []
    # このクライアントがLINEの誰にあたるかを紐づけるための情報（任意）。
    # 一度紐づければ、以降は client_initials だけで自動的に照合される。
    line_client_id: str | None = None
    line_display_name: str | None = None


class AuraChakraEnergy(BaseModel):
    chakra: str  # 例: "クラウンチャクラ", "サードアイチャクラ"
    energy_percent: float
    level: str | None = None  # 例: "低い", "中", "高い"
    chaos: int | None = None  # 「カオス」の数値（あれば）


class AuraFocusItem(BaseModel):
    chakra: str
    match_percent: float
    session_count: int | None = None
    code: str | None = None
    current_state: str  # 今の制限的な思い込み
    current_state_description: str | None = None  # チャクラカラーの説明など
    target_state: str  # 「目標とする状態」のアファメーション文
    target_state_description: str | None = None


class HealyAuraReport(BaseModel):
    # 個人情報保護のため、フルネームではなくイニシャルで保存する運用とする
    client_initials: str
    report_datetime: str
    main_focus: str | None = None  # 「主患部」のアファメーション文
    chakra_energies: list[AuraChakraEnergy] = []
    items: list[AuraFocusItem] = []
    line_client_id: str | None = None
    line_display_name: str | None = None


class ResonanceItem(BaseModel):
    topic: str  # 例: "アレルギー経路", "肌", "関節", "膀胱", "脂肪変性"
    match_percent: float


class HealyResonanceReport(BaseModel):
    # 個人情報保護のため、フルネームではなくイニシャルで保存する運用とする
    client_initials: str
    report_datetime: str
    main_focus: str | None = None  # 主患部（問いかけの形のことが多い）
    items: list[ResonanceItem] = []
    line_client_id: str | None = None
    line_display_name: str | None = None


class MeridianEnergy(BaseModel):
    meridian: str  # 例: "少陽三焦経経絡左", "胃経絡右"
    interference_percent: float  # 活動性低〜活動性高のスライダー値（負の値もあり）


class MeridianFocusItem(BaseModel):
    point_name: str  # 例: "3H 21「耳への門」耳門 (ermen)"
    match_percent: float  # 負の値もあり得る
    session_count: int | None = None
    code: str | None = None  # ホメオパシー的なコード（例: "D 24", "LM 0"）
    current_state_notes: list[str] = []  # 番号付きの課題記述
    target_state: str
    target_state_description: str | None = None


class MeridianProgramItem(BaseModel):
    name: str  # 例: "胆嚢", "肝臓", "トリプルヒーター", "ホルモンバランス"
    match_percent: float


class HealyMeridianReport(BaseModel):
    # 個人情報保護のため、フルネームではなくイニシャルで保存する運用とする
    client_initials: str
    report_datetime: str
    main_focus: str | None = None
    meridian_energies: list[MeridianEnergy] = []
    items: list[MeridianFocusItem] = []
    programs: list[MeridianProgramItem] = []
    line_client_id: str | None = None
    line_display_name: str | None = None


class ExternalGptEvent(BaseModel):
    source: str  # 例: 相手のGPT/サービス名
    message: str
    context: dict[str, Any] | None = None


@router.post("/api/healy-data")
def receive_healy_data(event: HealyEvent):
    record = {
        "received_at": datetime.now(timezone.utc).isoformat(),
        "source": event.source,
        "data": event.data,
    }
    append_healy_event(record)
    return {"status": "stored"}


@router.post("/api/healy-data/coaching-report")
async def receive_coaching_report(report: HealyCoachingReport):
    record = {
        "received_at": datetime.now(timezone.utc).isoformat(),
        "source": "healy_coaching_report",
        "data": report.model_dump(),
    }
    append_healy_event(record)

    client_id = report.line_client_id
    if client_id:
        storage.save_client_link(report.client_initials, client_id, report.line_display_name or "")
    else:
        client_id = storage.resolve_client_id_by_initials(report.client_initials)
        if not client_id and report.line_display_name:
            client_id = storage.resolve_client_id_by_display_name(report.line_display_name)
            if client_id:
                storage.save_client_link(report.client_initials, client_id, report.line_display_name)

    try:
        summary = await generate_reply(_build_summary_prompt(report), SUMMARY_SYSTEM_PROMPT)
        save_active_healy_summary(report.client_initials, summary)
    except Exception:
        logger.exception("Healy summary generation failed")

    if client_id:
        try:
            recent_messages = [
                m["message"] for m in storage.get_client_messages(client_id, limit=50)
            ]
            analysis_prompt = _build_analysis_prompt(report, recent_messages)
            analysis = await generate_reply(analysis_prompt, ANALYSIS_SYSTEM_PROMPT)
            storage.save_client_analysis(client_id, report.client_initials, analysis)
        except Exception:
            logger.exception("Healy analysis generation failed")

    return {"status": "stored", "linked_client_id": client_id}


@router.post("/api/healy-data/aura-report")
async def receive_aura_report(report: HealyAuraReport):
    record = {
        "received_at": datetime.now(timezone.utc).isoformat(),
        "source": "healy_aura_report",
        "data": report.model_dump(),
    }
    append_healy_event(record)

    client_id = report.line_client_id
    if client_id:
        storage.save_client_link(report.client_initials, client_id, report.line_display_name or "")
    else:
        client_id = storage.resolve_client_id_by_initials(report.client_initials)
        if not client_id and report.line_display_name:
            client_id = storage.resolve_client_id_by_display_name(report.line_display_name)
            if client_id:
                storage.save_client_link(report.client_initials, client_id, report.line_display_name)

    try:
        summary = await generate_reply(_build_aura_summary_prompt(report), AURA_SUMMARY_SYSTEM_PROMPT)
        save_active_healy_summary(report.client_initials, summary)
    except Exception:
        logger.exception("Aura summary generation failed")

    if client_id:
        try:
            recent_messages = [
                m["message"] for m in storage.get_client_messages(client_id, limit=50)
            ]
            analysis_prompt = _build_aura_analysis_prompt(report, recent_messages)
            analysis = await generate_reply(analysis_prompt, AURA_ANALYSIS_SYSTEM_PROMPT)
            storage.save_client_analysis(client_id, report.client_initials, analysis)
        except Exception:
            logger.exception("Aura analysis generation failed")

    return {"status": "stored", "linked_client_id": client_id}


@router.post("/api/healy-data/resonance-report")
async def receive_resonance_report(report: HealyResonanceReport):
    record = {
        "received_at": datetime.now(timezone.utc).isoformat(),
        "source": "healy_resonance_report",
        "data": report.model_dump(),
    }
    append_healy_event(record)

    client_id = report.line_client_id
    if client_id:
        storage.save_client_link(report.client_initials, client_id, report.line_display_name or "")
    else:
        client_id = storage.resolve_client_id_by_initials(report.client_initials)
        if not client_id and report.line_display_name:
            client_id = storage.resolve_client_id_by_display_name(report.line_display_name)
            if client_id:
                storage.save_client_link(report.client_initials, client_id, report.line_display_name)

    try:
        summary = await generate_reply(
            _build_resonance_summary_prompt(report), RESONANCE_SUMMARY_SYSTEM_PROMPT
        )
        save_active_healy_summary(report.client_initials, summary)
    except Exception:
        logger.exception("Resonance summary generation failed")

    if client_id:
        try:
            recent_messages = [
                m["message"] for m in storage.get_client_messages(client_id, limit=50)
            ]
            analysis_prompt = _build_resonance_analysis_prompt(report, recent_messages)
            analysis = await generate_reply(analysis_prompt, RESONANCE_ANALYSIS_SYSTEM_PROMPT)
            storage.save_client_analysis(client_id, report.client_initials, analysis)
        except Exception:
            logger.exception("Resonance analysis generation failed")

    return {"status": "stored", "linked_client_id": client_id}


@router.post("/api/healy-data/meridian-report")
async def receive_meridian_report(report: HealyMeridianReport):
    record = {
        "received_at": datetime.now(timezone.utc).isoformat(),
        "source": "healy_meridian_report",
        "data": report.model_dump(),
    }
    append_healy_event(record)

    client_id = report.line_client_id
    if client_id:
        storage.save_client_link(report.client_initials, client_id, report.line_display_name or "")
    else:
        client_id = storage.resolve_client_id_by_initials(report.client_initials)
        if not client_id and report.line_display_name:
            client_id = storage.resolve_client_id_by_display_name(report.line_display_name)
            if client_id:
                storage.save_client_link(report.client_initials, client_id, report.line_display_name)

    try:
        summary = await generate_reply(
            _build_meridian_summary_prompt(report), MERIDIAN_SUMMARY_SYSTEM_PROMPT
        )
        save_active_healy_summary(report.client_initials, summary)
    except Exception:
        logger.exception("Meridian summary generation failed")

    if client_id:
        try:
            recent_messages = [
                m["message"] for m in storage.get_client_messages(client_id, limit=50)
            ]
            analysis_prompt = _build_meridian_analysis_prompt(report, recent_messages)
            analysis = await generate_reply(analysis_prompt, MERIDIAN_ANALYSIS_SYSTEM_PROMPT)
            storage.save_client_analysis(client_id, report.client_initials, analysis)
        except Exception:
            logger.exception("Meridian analysis generation failed")

    return {"status": "stored", "linked_client_id": client_id}


@router.get("/api/healy-data")
def list_healy_data(limit: int = 50):
    return read_jsonl(storage.HEALY_LOG_FILE, limit=limit)


@router.post("/api/external-gpt")
def receive_external_gpt(event: ExternalGptEvent):
    record = {
        "received_at": datetime.now(timezone.utc).isoformat(),
        "source": event.source,
        "message": event.message,
        "context": event.context,
    }
    append_external_gpt_event(record)
    return {"status": "stored"}


@router.get("/api/external-gpt")
def list_external_gpt(limit: int = 50):
    return read_jsonl(storage.EXTERNAL_GPT_LOG_FILE, limit=limit)
