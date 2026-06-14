"""Report generation: summary tables, citation tables, JSON export."""

import json
from collections import Counter
from pathlib import Path

import pandas as pd

from src.comparator import shorten


def build_summary_df(comparison_results: list[dict]) -> pd.DataFrame:
    """Build a summary DataFrame from comparison results."""
    return pd.DataFrame([
        {
            'Dieu': item.get('dieu_number') or item['article_number'],
            'Khoan': item.get('khoan_number') or '0',
            'Dieu v2 match': item.get('matched_article_v2') or '(khong tim thay)',
            'Match score': item.get('match_score', 0.0),
            'Tieu de': item.get('article_title', ''),
            'Trang thai': item['status'],
            'Grounded': item.get('grounded', False),
            'Ket luan': shorten(item.get('conclusion', ''), 120),
        }
        for item in comparison_results
    ])


def build_citation_df(comparison_results: list[dict]) -> pd.DataFrame:
    """Build a citation DataFrame listing evidence per changed article."""
    rows = []
    for item in comparison_results:
        if item['status'] == 'unchanged':
            continue
        if not item.get('evidence'):
            rows.append({
                'Dieu': item.get('dieu_number') or item['article_number'],
                'Khoan': item.get('khoan_number') or '0',
                'Dieu v2 match': item.get('matched_article_v2') or '(khong tim thay)',
                'Loai': 'No evidence',
                'V1': '',
                'V2': '',
            })
            continue
        for ev in item['evidence']:
            rows.append({
                'Dieu': item.get('dieu_number') or item['article_number'],
                'Khoan': item.get('khoan_number') or '0',
                'Dieu v2 match': item.get('matched_article_v2') or '(khong tim thay)',
                'Loai': ev.get('tag', 'changed'),
                'V1': ev.get('before', ''),
                'V2': ev.get('after', ''),
            })
    return pd.DataFrame(rows)


def build_report(comparison_results: list[dict], config: dict) -> dict:
    """Build the full report payload dict."""
    status_counts = Counter(item['status'] for item in comparison_results)
    grounded_count = sum(1 for item in comparison_results if item.get('grounded'))
    llm_used_count = sum(1 for item in comparison_results if item.get('llm_used'))

    return {
        'config': {
            **config,
            'principle': 'Khong bang chung -> khong ket luan',
            'total_khoans': len(comparison_results),
            'status_counts': dict(status_counts),
            'llm_used_count': llm_used_count,
            'fallback_count': len(comparison_results) - llm_used_count,
            'grounded_count': grounded_count,
            'ungrounded_count': len(comparison_results) - grounded_count,
        },
        'article_level_results': comparison_results,
    }


def build_copilot_report(report: dict, max_items: int = 20) -> dict:
    """Build a compact payload that Copilot/chat can render reliably."""
    cfg = report.get('config', {})
    rows = report.get('article_level_results', [])

    changed_items = [
        item for item in rows
        if item.get('status') in {'changed', 'added', 'removed'}
    ]

    compact_items = []
    for item in changed_items[:max_items]:
        compact_items.append({
            'dieu': item.get('dieu_number') or item.get('article_number', ''),
            'khoan': item.get('khoan_number', '0'),
            'title': item.get('article_title', ''),
            'status': item.get('status', ''),
            'matched_v2': item.get('matched_article_v2') or '(khong tim thay)',
            'score': item.get('match_score', 0.0),
            'conclusion': shorten(item.get('conclusion', ''), 240),
        })

    return {
        'summary': {
            'file_v1': cfg.get('file_v1'),
            'file_v2': cfg.get('file_v2'),
            'total_khoans': cfg.get('total_khoans', 0),
            'status_counts': cfg.get('status_counts', {}),
            'llm_used_count': cfg.get('llm_used_count', 0),
            'grounded_count': cfg.get('grounded_count', 0),
        },
        'changed_items_limit': max_items,
        'changed_items_total': len(changed_items),
        'changed_items': compact_items,
    }


def render_copilot_text(copilot_report: dict) -> str:
    """Render a concise plain-text summary for terminal/Copilot display."""
    s = copilot_report.get('summary', {})
    counts = s.get('status_counts', {})
    lines = [
        '=== COMPARISON SUMMARY ===',
        f"V1: {s.get('file_v1', '')}",
        f"V2: {s.get('file_v2', '')}",
        f"Total khoans: {s.get('total_khoans', 0)}",
        (
            'Status: '
            f"unchanged={counts.get('unchanged', 0)}, "
            f"changed={counts.get('changed', 0)}, "
            f"added={counts.get('added', 0)}, "
            f"removed={counts.get('removed', 0)}"
        ),
        f"LLM used: {s.get('llm_used_count', 0)}",
        f"Grounded: {s.get('grounded_count', 0)}",
        '',
        '=== TOP CHANGES ===',
    ]

    changed = copilot_report.get('changed_items', [])
    if not changed:
        lines.append('(Khong co muc thay doi)')
        return '\n'.join(lines)

    for idx, item in enumerate(changed, start=1):
        lines.append(
            f"{idx}. Dieu {item.get('dieu')} - Khoan {item.get('khoan')} | "
            f"{item.get('status')} | score={item.get('score', 0.0):.2f}"
        )
        lines.append(f"   Tieu de: {item.get('title', '')}")
        lines.append(f"   Ket luan: {item.get('conclusion', '')}")

    return '\n'.join(lines)


def save_report_json(report: dict, output_path: Path) -> Path:
    """Write report payload to a JSON file. Returns the path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding='utf-8',
    )
    return output_path


def save_copilot_report_json(copilot_report: dict, output_path: Path) -> Path:
    """Write compact Copilot report JSON."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(copilot_report, ensure_ascii=False, indent=2, default=str),
        encoding='utf-8',
    )
    return output_path


def save_copilot_report_txt(copilot_text: str, output_path: Path) -> Path:
    """Write concise plain-text summary for quick display in chat/terminal."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(copilot_text, encoding='utf-8')
    return output_path
