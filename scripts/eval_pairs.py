"""Đánh giá độ chính xác của pipeline so với bản chuẩn CHANGELOG (.md).

Chạy toàn bộ các cặp trong data/document, gom kết quả khoản-level về cấp Điều,
rồi đối chiếu số Điều bị xoá / thêm mới / được sửa với bảng tổng kết trong file
CHANGELOG. Vì bản chuẩn đếm theo Điều còn chương trình chạy theo Khoản, đây là
phép so xấp xỉ ở cấp Điều (không phải khớp tuyệt đối).
"""

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.pipeline import run_comparison_pipeline  # noqa: E402

DOC_DIR = ROOT / 'data' / 'document'
OUT_DIR = ROOT / 'outputs' / 'eval_pairs'
OUT_DIR.mkdir(parents=True, exist_ok=True)


def pick_files(pair_dir: Path):
    """Trả về (v1, v2) docx. V2 = file có hậu tố v2; V1 = file còn lại."""
    docs = [f for f in pair_dir.glob('*.docx')
            if not f.name.startswith('~$') and 'changelog' not in f.name.lower()]
    if len(docs) < 2:
        return None, None
    v2 = next((f for f in docs if re.search(r'[_ ]?v2', f.stem, re.IGNORECASE)), None)
    if v2 is None:
        docs_sorted = sorted(docs, key=lambda p: p.name.lower())
        return docs_sorted[0], docs_sorted[1]
    v1 = next((f for f in docs if f != v2), None)
    return v1, v2


def find_changelog(pair_dir: Path):
    cands = [f for f in pair_dir.glob('*.md')]
    return cands[0] if cands else None


def parse_gold(md_path: Path) -> dict:
    """Trích số Điều bị xoá / thêm mới / được sửa từ bảng tổng kết."""
    text = md_path.read_text(encoding='utf-8')
    gold = {'removed': None, 'added': None, 'changed': None, 'khoan_removed': None}

    def first_int(s):
        m = re.search(r'(\d+)', s)
        return int(m.group(1)) if m else None

    for line in text.splitlines():
        low = line.lower()
        if '|' not in line:
            continue
        if 'điều bị xo' in low:
            gold['removed'] = first_int(line.split('|')[-2])
        elif 'khoản bị xo' in low:
            gold['khoan_removed'] = first_int(line.split('|')[-2])
        elif 'thêm mới' in low:
            gold['added'] = first_int(line.split('|')[-2])
        elif 'được sửa' in low or 'sửa nội dung' in low:
            gold['changed'] = first_int(line.split('|')[-2])
    return gold


def rollup_articles(rows: list[dict]) -> dict:
    """Gom kết quả khoản-level về cấp Điều.

    - removed: Điều (v1) mà MỌI khoản đều removed.
    - added:   Điều (v2) mà MỌI khoản đều added.
    - changed: Điều (v1) có ít nhất 1 khoản changed.
    """
    by_dieu_v1 = defaultdict(list)
    by_dieu_v2_added = defaultdict(list)
    for r in rows:
        status = r.get('status')
        dieu = str(r.get('dieu_number') or r.get('article_number') or '')
        if status == 'added':
            by_dieu_v2_added[dieu].append(status)
        else:
            by_dieu_v1[dieu].append(status)

    removed_articles = [d for d, sts in by_dieu_v1.items()
                        if sts and all(s == 'removed' for s in sts)]
    changed_articles = [d for d, sts in by_dieu_v1.items()
                        if any(s == 'changed' for s in sts)]
    added_articles = list(by_dieu_v2_added.keys())

    # khoản bị xoá lẻ: Điều có cả removed lẫn (changed/unchanged)
    partial_removed_khoan = sum(
        1 for sts in by_dieu_v1.values()
        for s in sts if s == 'removed'
    ) - sum(len(by_dieu_v1[d]) for d in removed_articles)

    return {
        'art_removed': len(removed_articles),
        'art_added': len(added_articles),
        'art_changed': len(changed_articles),
        'khoan_removed_partial': partial_removed_khoan,
        'removed_articles': sorted(removed_articles),
        'added_articles': sorted(added_articles),
        'changed_articles': sorted(changed_articles),
    }


def main():
    pairs = sorted([p for p in DOC_DIR.glob('pair *') if p.is_dir()],
                   key=lambda p: int(re.search(r'\d+', p.name).group()))
    summary = []
    for pair_dir in pairs:
        v1, v2 = pick_files(pair_dir)
        md = find_changelog(pair_dir)
        if not v1 or not v2 or not md:
            print(f'[SKIP] {pair_dir.name}: thiếu file')
            continue
        print(f'\n{"="*70}\n[RUN] {pair_dir.name}\n  V1={v1.name}\n  V2={v2.name}')
        try:
            res = run_comparison_pipeline(
                file_v1=v1, file_v2=v2,
                chroma_dir=ROOT / 'chroma_db',
                output_dir=OUT_DIR / pair_dir.name.replace(' ', '_'),
            )
        except Exception as e:
            print(f'  [ERROR] {e}')
            continue
        rows = res['report']['article_level_results']
        counts = Counter(r['status'] for r in rows)
        roll = rollup_articles(rows)
        gold = parse_gold(md)
        rec = {
            'pair': pair_dir.name,
            'khoan_counts': dict(counts),
            'rollup': roll,
            'gold': gold,
        }
        summary.append(rec)
        print(f'  KHOAN : {dict(counts)}')
        print(f'  ROLLUP: removed_art={roll["art_removed"]} '
              f'added_art={roll["art_added"]} changed_art={roll["art_changed"]}')
        print(f'  GOLD  : removed={gold["removed"]} added={gold["added"]} '
              f'changed={gold["changed"]} khoan_removed={gold["khoan_removed"]}')

    out = OUT_DIR / 'eval_summary.json'
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')

    print(f'\n\n{"#"*70}\n# BẢNG TỔNG HỢP (article-level)\n{"#"*70}')
    print(f'{"pair":<9}| {"removed (prog/gold)":<20}| {"added (prog/gold)":<18}| changed (prog/gold)')
    for rec in summary:
        r = rec['rollup']; g = rec['gold']
        print(f'{rec["pair"]:<9}| '
              f'{str(r["art_removed"])+"/"+str(g["removed"]):<20}| '
              f'{str(r["art_added"])+"/"+str(g["added"]):<18}| '
              f'{r["art_changed"]}/{g["changed"]}')
    print(f'\nĐã lưu chi tiết: {out}')


if __name__ == '__main__':
    main()
