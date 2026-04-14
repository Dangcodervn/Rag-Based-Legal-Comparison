"""Reusable UI components for rendering comparison reports."""

import pandas as pd
import streamlit as st


# ── Status icons ─────────────────────────────────────────────────────

STATUS_ICONS = {
    'unchanged': '🟢',
    'changed': '🟡',
    'added': '🔵',
    'removed': '🔴',
}

STATUS_LABELS = {
    'unchanged': 'Khong doi',
    'changed': 'Sua doi',
    'added': 'Them moi',
    'removed': 'Xoa bo',
}


# ── Overview metrics ─────────────────────────────────────────────────

def render_metrics(report: dict):
    """Display top-level summary metrics."""
    cfg = report.get('config', {})
    status = cfg.get('status_counts', {})
    total = cfg.get('total_articles', 0)

    changed = status.get('changed', 0)
    added = status.get('added', 0)
    removed = status.get('removed', 0)
    unchanged = status.get('unchanged', 0)

    cols = st.columns(4)
    cols[0].metric("Tong so Dieu", total)
    cols[1].metric("🟡 Sua doi", changed)
    cols[2].metric("🔵 Them moi / 🔴 Xoa bo", f"{added} / {removed}")
    cols[3].metric("🟢 Khong doi", unchanged)


# ── 1. Change list: only changed/added/removed ──────────────────────

def render_change_list(comparison_results: list[dict]):
    """Render a concise list of changes (skip unchanged articles)."""
    changes = [r for r in comparison_results if r['status'] != 'unchanged']

    if not changes:
        st.success("Khong co thay doi nao giua hai phien ban.")
        return

    for item in changes:
        icon = STATUS_ICONS.get(item['status'], '⚪')
        label = STATUS_LABELS.get(item['status'], item['status'])
        article = item['article_number']
        title = item.get('article_title', '')

        header = f"{icon} **[{label}]** {article}"
        if title:
            header += f" — {title}"

        # Location info
        location_parts = []
        if item.get('chuong'):
            location_parts.append(item['chuong'])
        if item.get('muc'):
            location_parts.append(item['muc'])
        location = " > ".join(location_parts) if location_parts else ""

        with st.expander(header, expanded=True):
            if location:
                st.caption(f"📍 Vi tri: {location}")

            # Conclusion from LLM
            if item.get('conclusion'):
                st.markdown(f"> {item['conclusion']}")

            # Evidence excerpts
            if item.get('evidence'):
                st.markdown("**Trich doan thay doi:**")
                for i, ev in enumerate(item['evidence'], 1):
                    tag = ev.get('tag', 'changed')
                    tag_icon = '✏️' if tag == 'changed' else ('➕' if tag == 'added' else '➖')
                    st.markdown(f"*{i}. {tag_icon} {tag}*")
                    c1, c2 = st.columns(2)
                    with c1:
                        st.markdown("**V1 (cu):**")
                        st.code(ev.get('before', '(khong co)'), language=None)
                    with c2:
                        st.markdown("**V2 (moi):**")
                        st.code(ev.get('after', '(khong co)'), language=None)


# ── 2. Key changes summary ──────────────────────────────────────────

def render_key_summary(comparison_results: list[dict]):
    """Render a summary of important change points."""
    changes = [r for r in comparison_results if r['status'] != 'unchanged']

    if not changes:
        st.info("Khong co thay doi.")
        return

    # Group by status
    by_status = {}
    for item in changes:
        by_status.setdefault(item['status'], []).append(item)

    for status in ['changed', 'added', 'removed']:
        items = by_status.get(status, [])
        if not items:
            continue
        icon = STATUS_ICONS[status]
        label = STATUS_LABELS[status]
        st.markdown(f"### {icon} {label} ({len(items)} dieu)")
        for item in items:
            article = item['article_number']
            conclusion = item.get('conclusion', '(khong co ket luan)')
            st.markdown(f"- **{article}**: {conclusion}")


# ── 3. Citation / excerpt table ──────────────────────────────────────

def render_citations(comparison_results: list[dict]):
    """Render evidence excerpts with article location."""
    rows = []
    for item in comparison_results:
        if item['status'] == 'unchanged':
            continue
        if not item.get('evidence'):
            rows.append({
                'Dieu': item['article_number'],
                'Trang thai': f"{STATUS_ICONS.get(item['status'],'')} {item['status']}",
                'Loai': '—',
                'Trich doan V1': '(khong co bang chung)',
                'Trich doan V2': '',
            })
            continue
        for ev in item['evidence']:
            rows.append({
                'Dieu': item['article_number'],
                'Trang thai': f"{STATUS_ICONS.get(item['status'],'')} {item['status']}",
                'Loai': ev.get('tag', 'changed'),
                'Trich doan V1': ev.get('before', ''),
                'Trich doan V2': ev.get('after', ''),
            })

    if not rows:
        st.info("Khong co trich dan.")
        return

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
