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
            'Dieu v1': item['article_number'],
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
                'Dieu v1': item['article_number'],
                'Dieu v2 match': item.get('matched_article_v2') or '(khong tim thay)',
                'Loai': 'No evidence',
                'V1': '',
                'V2': '',
            })
            continue
        for ev in item['evidence']:
            rows.append({
                'Dieu v1': item['article_number'],
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
            'total_articles': len(comparison_results),
            'status_counts': dict(status_counts),
            'llm_used_count': llm_used_count,
            'fallback_count': len(comparison_results) - llm_used_count,
            'grounded_count': grounded_count,
            'ungrounded_count': len(comparison_results) - grounded_count,
        },
        'article_level_results': comparison_results,
    }


def save_report_json(report: dict, output_path: Path) -> Path:
    """Write report payload to a JSON file. Returns the path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str),
        encoding='utf-8',
    )
    return output_path
