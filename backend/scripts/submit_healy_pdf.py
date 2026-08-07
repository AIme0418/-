"""HealyアプリからエクスポートしたPDFを読み込み、対応するAPIエンドポイントに投入するスクリプト。

対応するレポート種類: コーチング分析・オーラ分析・レゾナンス分析・経絡分析。
PDFの1行目のタイトルから種類を自動判定する。

デフォルトはドライラン（解析結果を表示するだけで、実際には送信しない）。
内容を目視で確認してから --submit を付けて実行すること。PDFのレイアウトが
少しでも変わると解析が崩れる可能性があるため、必ず内容を確認してから投入する。

使い方:
    python scripts/submit_healy_pdf.py <PDFファイルパス>
    python scripts/submit_healy_pdf.py <PDFファイルパス> --submit
    python scripts/submit_healy_pdf.py <PDFファイルパス> --submit --line-client-id U1234 --line-display-name たろう
    python scripts/submit_healy_pdf.py <PDFファイルパス> --client-initials M.I. --submit
"""

import argparse
import json
import re
import sys
from pathlib import Path

import httpx
import pypdf

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

BACKEND_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BACKEND_DIR / ".env"

REPORT_TYPE_TITLES = {
    "コーチング分析": "coaching",
    "オーラ分析": "aura",
    "レゾナンス分析": "resonance",
    "経絡分析": "meridian",
}

ENDPOINT_BY_TYPE = {
    "coaching": "/api/healy-data/coaching-report",
    "aura": "/api/healy-data/aura-report",
    "resonance": "/api/healy-data/resonance-report",
    "meridian": "/api/healy-data/meridian-report",
}

DATE_RE = re.compile(r"(\d{1,2})月\s*(\d{1,2}),\s*(\d{4})\s*\|\s*(\d{1,2}):(\d{2})")
NAME_RE = re.compile(r"^([A-Z][a-z]+(?:[A-Z][a-z]+)+)$", re.MULTILINE)


def clean(s: str | None) -> str | None:
    return re.sub(r"\s+", "", s) if s else s


def load_admin_token() -> str:
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("ADMIN_API_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError(f"ADMIN_API_TOKEN が {ENV_FILE} に見つかりません")


def extract_text(pdf_path: Path) -> str:
    reader = pypdf.PdfReader(str(pdf_path))
    return "\f".join((page.extract_text() or "") for page in reader.pages)


def detect_report_type(text: str) -> str:
    first_line = text.strip().splitlines()[0].strip()
    for title, report_type in REPORT_TYPE_TITLES.items():
        if title in first_line:
            return report_type
    raise ValueError(f"レポート種類を判定できませんでした（1行目: {first_line!r}）")


def parse_datetime(text: str) -> str:
    m = DATE_RE.search(text)
    if not m:
        raise ValueError("日時が見つかりませんでした")
    month, day, year, hour, minute = m.groups()
    return f"{year}-{int(month):02d}-{int(day):02d}T{int(hour):02d}:{minute}:00+09:00"


def detect_client_initials(text: str) -> str | None:
    m = NAME_RE.search(text)
    if not m:
        return None
    # "MegumiIchimura" のようにスペースなしで連結された氏名を、大文字境界で分割する
    parts = re.findall(r"[A-Z][a-z]+", m.group(1))
    if not parts:
        return None
    return "".join(f"{p[0].upper()}." for p in parts)


def parse_coaching(text: str) -> dict:
    mf_m = re.search(r"主患部\n(.+?。)", text, re.DOTALL)
    main_focus = clean(mf_m.group(1)) if mf_m else None

    item_re = re.compile(
        r"([^\s。、\n]{1,15}?)\s*(-?\d+)%\s+(\d+)\s+(\S+?)\s*\n?目標とする状態[:：]\s*\n?(.+?)"
        r"(?=[^\s。、\n]{1,15}?\s*-?\d+%\s+\d+\s+\S+?\s*\n?目標とする状態[:：]|アプリを開く|\Z)",
        re.DOTALL,
    )
    items = []
    for m in item_re.finditer(text):
        category, percent, count, code, target = m.groups()
        items.append(
            {
                "category": category,
                "match_percent": float(percent),
                "session_count": int(count),
                "code": code,
                "target_state": clean(target),
            }
        )
    return {"main_focus": main_focus, "items": items}


def parse_aura(text: str) -> dict:
    mf_m = re.search(r"主患部\n(.+?。)", text, re.DOTALL)
    main_focus = clean(mf_m.group(1)) if mf_m else None

    first_item_m = re.search(r"\S+?\s+\d+%\s+\d+\s+\S+\s*現在の状態", text)
    energies = []
    if mf_m and first_item_m:
        energy_section = text[mf_m.end() : first_item_m.start()]
        energy_re = re.compile(r"([^\d\n]+?)(?:\s*カオス\s*(\d+))?\n?エネルギー(\d+)%-?(低い|中|高い)?")
        for m in energy_re.finditer(energy_section):
            name, chaos, pct, level = m.groups()
            name = name.strip()
            if not name or name == "総エネルギー":
                continue
            energies.append(
                {
                    "chakra": name,
                    "energy_percent": float(pct),
                    "level": level,
                    "chaos": int(chaos) if chaos else None,
                }
            )

    item_re = re.compile(
        r"(\S+?)\s+(-?\d+)%\s+(\d+)\s+(\S+)\s*"
        r"現在の状態[:：]\s*(.+?)\s*"
        r"現在の状態の説明[:：]\s*(.+?)\s*"
        r"目標とする状態[:：]\s*(.+?)\s*"
        r"目標とする状態説明[:：]\s*(.+?)"
        r"(?=\S+?\s+-?\d+%\s+\d+\s+\S+\s*現在の状態|アプリを開く|\Z)",
        re.DOTALL,
    )
    items = []
    for m in item_re.finditer(text):
        chakra, percent, count, code, cur, cur_desc, tgt, tgt_desc = m.groups()
        items.append(
            {
                "chakra": chakra,
                "match_percent": float(percent),
                "session_count": int(count),
                "code": code,
                "current_state": clean(cur),
                "current_state_description": clean(cur_desc),
                "target_state": clean(tgt),
                "target_state_description": clean(tgt_desc),
            }
        )
    return {"main_focus": main_focus, "chakra_energies": energies, "items": items}


def parse_resonance(text: str) -> dict:
    m = re.search(r"主患部\n(.+?)\n(.+?)アプリを開く", text, re.DOTALL)
    if not m:
        raise ValueError("主患部/項目セクションが見つかりませんでした")
    main_focus = m.group(1).strip()
    body = m.group(2)
    items = [
        {"topic": t.strip(), "match_percent": float(p)}
        for t, p in re.findall(r"(\D+?)\n?(\d+)%", body)
    ]
    return {"main_focus": main_focus, "items": items}


def parse_meridian(text: str) -> dict:
    mf_m = re.search(r"主患部\n(.+?。)", text, re.DOTALL)
    main_focus = clean(mf_m.group(1)) if mf_m else None

    energies = []
    energy_section_m = re.search(r"干渉性概要\n(.+?)データベース", text, re.DOTALL)
    if energy_section_m:
        energy_re = re.compile(r"([^\d\n(（]+?)\s*[\(（]\s*(-?\d+)%\s*[\)）]\s*活動性低\s*干渉性\s*活動性高")
        energies = [
            {"meridian": m.group(1).strip(), "interference_percent": float(m.group(2))}
            for m in energy_re.finditer(energy_section_m.group(1))
        ]

    items = []
    db_section_m = re.search(r"データベース\n(.+?)プログラム", text, re.DOTALL)
    if db_section_m:
        db_section = db_section_m.group(1)
        header_re = re.compile(r"(\d+[A-Za-z]?\d*「[^」]+」\S+?)\s+(-?\d+)%\s+(\d+)\s+(\S+)\s*")
        headers = list(header_re.finditer(db_section))
        for i, hm in enumerate(headers):
            point, percent, count, code = hm.groups()
            body_start = hm.end()
            body_end = headers[i + 1].start() if i + 1 < len(headers) else len(db_section)
            body = db_section[body_start:body_end]

            tgt_m = re.search(
                r"目標とする状態[:：]\s*(.+?)\s*(?:目標とする状態説明[:：]\s*(.+))?$", body, re.DOTALL
            )
            notes_text = clean(body[: tgt_m.start()]) if tgt_m else clean(body)
            target = clean(tgt_m.group(1)) if tgt_m else ""
            target_desc = clean(tgt_m.group(2)) if tgt_m and tgt_m.group(2) else None
            notes = (
                re.findall(r"\d+\.(.+?)(?=\d+\.|$)", notes_text)
                if notes_text and re.match(r"\d+\.", notes_text)
                else ([notes_text] if notes_text else [])
            )
            items.append(
                {
                    "point_name": point.strip(),
                    "match_percent": float(percent),
                    "session_count": int(count),
                    "code": code,
                    "current_state_notes": notes,
                    "target_state": target,
                    "target_state_description": target_desc,
                }
            )

    programs = []
    prog_m = re.search(r"プログラム\n(.+?)アプリを開く", text, re.DOTALL)
    if prog_m:
        programs = [
            {"name": t.strip(), "match_percent": float(p)}
            for t, p in re.findall(r"(\D+?)\n?(\d+)%", prog_m.group(1))
        ]

    return {"main_focus": main_focus, "meridian_energies": energies, "items": items, "programs": programs}


PARSERS = {
    "coaching": parse_coaching,
    "aura": parse_aura,
    "resonance": parse_resonance,
    "meridian": parse_meridian,
}


def print_preview(report_type: str, payload: dict) -> None:
    print(f"\n=== レポート種類: {report_type} ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    item_count = len(payload.get("items", []))
    print(f"\n項目数: {item_count} 件")
    print("内容をよく確認してください。問題なければ --submit を付けて再実行してください。")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pdf_path", type=Path, help="Healy分析PDFのパス")
    parser.add_argument("--client-initials", help="クライアントのイニシャル（PDFから氏名を自動検出できない場合は必須）")
    parser.add_argument("--line-client-id", help="紐づけるLINEのuser_id（任意）")
    parser.add_argument("--line-display-name", help="紐づけるLINEの表示名（任意）")
    parser.add_argument("--base-url", default="http://localhost:8000", help="バックエンドのURL（デフォルト: ローカル）")
    parser.add_argument("--submit", action="store_true", help="実際にAPIへ送信する（省略時はドライラン）")
    args = parser.parse_args()

    if not args.pdf_path.exists():
        print(f"ファイルが見つかりません: {args.pdf_path}", file=sys.stderr)
        sys.exit(1)

    text = extract_text(args.pdf_path)
    report_type = detect_report_type(text)
    report_datetime = parse_datetime(text)
    client_initials = args.client_initials or detect_client_initials(text)

    if not client_initials:
        print(
            "クライアントのイニシャルを自動検出できませんでした。"
            " --client-initials M.I. のように指定してください。",
            file=sys.stderr,
        )
        sys.exit(1)

    payload = PARSERS[report_type](text)
    payload["client_initials"] = client_initials
    payload["report_datetime"] = report_datetime
    if args.line_client_id:
        payload["line_client_id"] = args.line_client_id
    if args.line_display_name:
        payload["line_display_name"] = args.line_display_name

    if not payload.get("items"):
        print("警告: 項目が1件も解析できませんでした。PDFのレイアウトが想定と違う可能性があります。", file=sys.stderr)

    print_preview(report_type, payload)

    if not args.submit:
        print("\n(ドライランのため送信していません)")
        return

    token = load_admin_token()
    url = args.base_url.rstrip("/") + ENDPOINT_BY_TYPE[report_type]
    res = httpx.post(url, json=payload, headers={"Authorization": f"Bearer {token}"}, timeout=30.0)
    print(f"\n送信結果: {res.status_code} {res.text}")


if __name__ == "__main__":
    main()
