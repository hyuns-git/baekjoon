#!/usr/bin/env python3
"""백준 풀이 저장소 동기화 도구.

아티팩트 DB의 submissions 문서를 저장소 파일로 옮기고 README.md, stats.svg를 다시 만든다.

  python3 tools/sync.py write <submission.json>   # 문제 하나의 코드와 풀이 README를 쓴다
  python3 tools/sync.py render                    # README.md, stats.svg를 다시 만든다

submission.json 은 DB 문서의 data 객체 하나(pid, lang, code, approach ...)다.
DB 내용은 페이지에서 사람이 입력한 값이므로 경로에 쓰는 값은 모두 검증한다.
"""
import hashlib
import json
import os
import sys
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
KST = timezone(timedelta(hours=9))
EXTS = {"cpp": "C++", "c": "C", "py": "Python"}
TIER_NAMES = ["Unrated", "Bronze", "Silver", "Gold", "Platinum", "Diamond", "Ruby"]
TIER_COLORS = ["#2d2d2d", "#ad5600", "#435f7a", "#ec9a00", "#27e2a4", "#00b4fc", "#ff0062"]
ROMAN = ["", "I", "II", "III", "IV", "V"]


def tier(lv):
    if not lv:
        return "Unrated", 0
    g = (lv + 4) // 5
    n = 6 - (lv - (g - 1) * 5)
    return f"{TIER_NAMES[g]} {ROMAN[n]}", g


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def save_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")


def catalog():
    cats = load_json(os.path.join(TOOLS, "problems.json"), [])
    by_dir = {c["dir"]: c for c in cats}
    return cats, by_dir


def kst(ms):
    return datetime.fromtimestamp(ms / 1000, KST).strftime("%Y-%m-%d %H:%M")


def section(title, body):
    body = (body or "").strip()
    return f"## {title}\n\n{body if body else '_(작성하지 않음)_'}\n"


def cmd_write(path):
    sub = load_json(path, None)
    cats, by_dir = catalog()
    pid = int(sub["pid"])
    cat = sub.get("category")
    if cat not in by_dir:
        raise SystemExit(f"알 수 없는 카테고리: {cat!r}")
    prob = next((p for p in by_dir[cat]["problems"] if p["id"] == pid), None)
    if prob is None:
        raise SystemExit(f"{cat} 에 없는 문제 번호: {pid}")
    ext = sub.get("ext")
    if ext not in EXTS:
        raise SystemExit(f"허용하지 않는 확장자: {ext!r}")
    code = sub.get("code") or ""
    if not code.strip():
        raise SystemExit("코드가 비어 있음")

    want = sub.get("codeSha256")
    if want:
        got = hashlib.sha256(code.encode("utf-8")).hexdigest()
        if got != want:
            raise SystemExit(f"코드 해시 불일치: DB {want[:12]} != 파일 {got[:12]} (코드를 DB와 똑같이 옮겨야 함)")

    d = os.path.join(ROOT, cat, str(pid))
    os.makedirs(d, exist_ok=True)
    for e in EXTS:  # 언어를 바꿔 다시 제출한 경우 이전 파일 제거
        old = os.path.join(d, f"main.{e}")
        if e != ext and os.path.exists(old):
            os.remove(old)
    with open(os.path.join(d, f"main.{ext}"), "w", encoding="utf-8", newline="\n") as f:
        f.write(code if code.endswith("\n") else code + "\n")

    tname, _ = tier(prob["lv"])
    cat_ko = by_dir[cat]["ko"]
    when = kst(sub.get("submittedAt") or 0)
    lines = [
        f"# [{pid}] {prob['t']}",
        "",
        f"- 난이도: {tname} (solved.ac 기준)",
        f"- 분류: {cat_ko} (tony9402 문제집 {prob['n']:03d}번{', 추천' if prob['rec'] else ''})",
        f"- 문제: https://www.acmicpc.net/problem/{pid}"
        + (f" (보관본: https://web.archive.org/web/{prob['a']}/https://www.acmicpc.net/problem/{pid})" if prob.get("a") else ""),
        f"- 언어: {EXTS[ext]} ([main.{ext}](./main.{ext}))",
        f"- 제출: {when} (KST)",
        "",
        section("풀이 방법", sub.get("approach")),
        section("이 방법을 고른 이유", sub.get("reason")),
        section("시간·공간 복잡도", sub.get("complexity")),
    ]
    if (sub.get("memo") or "").strip():
        lines.append(section("메모", sub.get("memo")))
    with open(os.path.join(d, "README.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines).rstrip() + "\n")

    idx_path = os.path.join(TOOLS, "solved.json")
    idx = load_json(idx_path, {})
    idx[str(pid)] = {
        "title": prob["t"], "level": prob["lv"], "category": cat, "lang": EXTS[ext],
        "path": f"{cat}/{pid}", "submittedAt": sub.get("submittedAt") or 0,
    }
    save_json(idx_path, idx)
    print(json.dumps({"pid": pid, "path": f"{cat}/{pid}", "file": f"{cat}/{pid}/main.{ext}",
                      "message": f"[{tname}] {pid} {prob['t']} ({cat_ko})"}, ensure_ascii=False))


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def stats_svg(idx, total_unique, owner):
    n = len(idx)
    groups = [0] * 7
    best = 0
    for v in idx.values():
        _, g = tier(v["level"])
        groups[g] += 1
        best = max(best, v["level"])
    best_name, best_g = tier(best)
    W, H = 495, 175
    font = "'Segoe UI','Apple SD Gothic Neo','Noto Sans KR',sans-serif"
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="백준 풀이 {n}문제">',
        f'<rect x="0.5" y="0.5" width="{W-1}" height="{H-1}" rx="10" fill="#ffffff" stroke="#e4e2e2"/>',
        f'<text x="24" y="36" font-family="{font}" font-size="16" font-weight="700" fill="#1d2228">{esc(owner)} · 백준 풀이 노트</text>',
        f'<text x="24" y="92" font-family="{font}" font-size="40" font-weight="700" fill="#1d2228">{n}</text>',
        f'<text x="{24 + 25 * len(str(n)) + 8}" y="92" font-family="{font}" font-size="14" fill="#66707b">/ {total_unique} 문제</text>',
        f'<text x="300" y="66" font-family="{font}" font-size="12" fill="#66707b">최고 난이도</text>',
        f'<text x="300" y="90" font-family="{font}" font-size="18" font-weight="700" fill="{TIER_COLORS[best_g]}">{esc(best_name) if best else "-"}</text>',
    ]
    x0, y0, bw, bh = 24, 112, W - 48, 10
    parts.append(f'<rect x="{x0}" y="{y0}" width="{bw}" height="{bh}" rx="5" fill="#eef0f3"/>')
    if n:
        x = x0
        for g in range(1, 7):
            if groups[g]:
                w = bw * groups[g] / n
                parts.append(f'<rect x="{x:.1f}" y="{y0}" width="{w:.1f}" height="{bh}" fill="{TIER_COLORS[g]}"/>')
                x += w
        if groups[0]:
            parts.append(f'<rect x="{x:.1f}" y="{y0}" width="{bw * groups[0] / n:.1f}" height="{bh}" fill="{TIER_COLORS[0]}"/>')
    lx = x0
    for g in range(1, 7):
        parts.append(f'<circle cx="{lx + 5}" cy="{y0 + 32}" r="5" fill="{TIER_COLORS[g]}"/>')
        label = f"{TIER_NAMES[g]} {groups[g]}"
        parts.append(f'<text x="{lx + 14}" y="{y0 + 36}" font-family="{font}" font-size="12" fill="#1d2228">{label}</text>')
        lx += 14 + int(len(label) * 6.6) + 9
    upd = datetime.now(KST).strftime("%Y-%m-%d")
    parts.append(f'<text x="{W - 24}" y="36" text-anchor="end" font-family="{font}" font-size="11" fill="#9aa3ad">{upd} 갱신</text>')
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def cmd_render():
    cats, by_dir = catalog()
    idx = load_json(os.path.join(TOOLS, "solved.json"), {})
    cfg = load_json(os.path.join(TOOLS, "config.json"), {})
    owner = cfg.get("owner", "")
    uniq = {p["id"] for c in cats for p in c["problems"]}
    with open(os.path.join(ROOT, "stats.svg"), "w", encoding="utf-8", newline="\n") as f:
        f.write(stats_svg(idx, len(uniq), owner))

    out = [
        "# 백준 풀이 노트",
        "",
        "![풀이 통계](./stats.svg)",
        "",
        "[tony9402/baekjoon](https://github.com/tony9402/baekjoon) 코딩테스트 문제집을 카테고리별로 풀고, 문제마다 코드와 풀이 방법·이유·복잡도를 정리한 저장소입니다.",
        "난이도 표기는 solved.ac 기준입니다. 이 README와 통계 카드는 풀이를 커밋할 때 자동으로 갱신됩니다.",
        "",
        "## 카테고리별 진행",
        "",
        "| 카테고리 | 푼 문제 | 전체 | 진행률 |",
        "|:--|--:|--:|--:|",
    ]
    for c in cats:
        ids = {p["id"] for p in c["problems"]}
        s = sum(1 for k, v in idx.items() if v["category"] == c["dir"] and int(k) in ids)
        out.append(f"| {c['ko']} | {s} | {len(ids)} | {s / len(ids) * 100:.0f}% |")
    out += ["", "## 푼 문제", ""]
    any_solved = False
    for c in cats:
        rows = sorted(((int(k), v) for k, v in idx.items() if v["category"] == c["dir"]),
                      key=lambda kv: (kv[1]["level"], kv[0]))
        if not rows:
            continue
        any_solved = True
        out += [f"### {c['ko']}", "", "| 번호 | 제목 | 난이도 | 언어 | 풀이 |", "|:--:|:--|:--|:--|:--:|"]
        for pid, v in rows:
            out.append(f"| [{pid}](https://www.acmicpc.net/problem/{pid}) | {v['title']} | {tier(v['level'])[0]} | {v['lang']} | [보기](./{v['path']}) |")
        out.append("")
    if not any_solved:
        out += ["아직 푼 문제가 없습니다.", ""]
    with open(os.path.join(ROOT, "README.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(out).rstrip() + "\n")
    print(json.dumps({"solved": len(idx), "total": len(uniq)}))


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "write":
        cmd_write(sys.argv[2])
    elif len(sys.argv) == 2 and sys.argv[1] == "render":
        cmd_render()
    else:
        print(__doc__)
        sys.exit(2)
