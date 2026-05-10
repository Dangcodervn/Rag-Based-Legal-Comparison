"""Reusable UI components for rendering comparison reports."""

import difflib
import html

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


# ── Side-by-side diff ─────────────────────────────────────────────────

def _split_lines(text: str | None) -> list[str]:
    if not text:
        return []
    return str(text).splitlines()


def _build_line_diff_rows(v1_text: str | None, v2_text: str | None) -> list[dict]:
    """Build aligned line-level diff rows for side-by-side rendering."""
    v1_lines = _split_lines(v1_text)
    v2_lines = _split_lines(v2_text)
    matcher = difflib.SequenceMatcher(None, v1_lines, v2_lines)
    rows = []
    block_seq = 1

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            for offset in range(i2 - i1):
                rows.append({
                    'op': 'equal',
                    'block_id': '',
                    'v1_no': i1 + offset + 1,
                    'v1_text': v1_lines[i1 + offset],
                    'v2_no': j1 + offset + 1,
                    'v2_text': v2_lines[j1 + offset],
                })
            continue

        block_id = f"B{block_seq}"
        block_seq += 1

        if tag == 'delete':
            for idx in range(i1, i2):
                rows.append({
                    'op': 'delete',
                    'block_id': block_id,
                    'v1_no': idx + 1,
                    'v1_text': v1_lines[idx],
                    'v2_no': '',
                    'v2_text': '',
                })
            continue

        if tag == 'insert':
            for idx in range(j1, j2):
                rows.append({
                    'op': 'insert',
                    'block_id': block_id,
                    'v1_no': '',
                    'v1_text': '',
                    'v2_no': idx + 1,
                    'v2_text': v2_lines[idx],
                })
            continue

        max_len = max(i2 - i1, j2 - j1)
        for offset in range(max_len):
            left_idx = i1 + offset
            right_idx = j1 + offset
            rows.append({
                'op': 'replace',
                'block_id': block_id,
                'v1_no': left_idx + 1 if left_idx < i2 else '',
                'v1_text': v1_lines[left_idx] if left_idx < i2 else '',
                'v2_no': right_idx + 1 if right_idx < j2 else '',
                'v2_text': v2_lines[right_idx] if right_idx < j2 else '',
            })

    return rows


def render_side_by_side_diff(item: dict):
    """Render v1/v2 article text with line-level highlights."""
    v1_text = item.get('v1_text')
    v2_text = item.get('v2_text')
    if not v1_text and not v2_text:
        return

    rows = _build_line_diff_rows(v1_text, v2_text)
    if not rows:
        st.info("Khong co noi dung de hien thi.")
        return

    html_rows = []
    for row in rows:
        op = html.escape(str(row['op']))
        block_id = html.escape(str(row.get('block_id') or ''))
        html_rows.append(
            '<tr class="diff-row diff-{op}">'
            '<td class="line-no">{block_badge}{v1_no}</td>'
            '<td class="line-text">{v1_text}</td>'
            '<td class="line-no">{v2_no}</td>'
            '<td class="line-text">{v2_text}</td>'
            '</tr>'.format(
                op=op,
                block_badge=(
                    f'<span class="block-badge">{block_id}</span>' if block_id else ''
                ),
                v1_no=html.escape(str(row['v1_no'])),
                v1_text=html.escape(row['v1_text']),
                v2_no=html.escape(str(row['v2_no'])),
                v2_text=html.escape(row['v2_text']),
            )
        )

    st.markdown(
        """
<style>
.side-by-side-diff {
  border: 1px solid #e5e7eb;
  border-radius: 10px;
  max-height: 520px;
  overflow: auto;
}
.side-by-side-diff table {
  border-collapse: collapse;
  table-layout: fixed;
  width: 100%;
  font-size: 0.9rem;
}
.side-by-side-diff th {
  background: #f8fafc;
  border-bottom: 1px solid #e5e7eb;
  color: #334155;
  padding: 8px;
  position: sticky;
  text-align: left;
  top: 0;
  z-index: 1;
}
.side-by-side-diff td {
  border-bottom: 1px solid #f1f5f9;
  padding: 7px 8px;
  vertical-align: top;
}
.side-by-side-diff .line-no {
  color: #64748b;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  text-align: right;
  user-select: none;
  width: 48px;
}
.side-by-side-diff .block-badge {
  background: #e0f2fe;
  border: 1px solid #bae6fd;
  border-radius: 999px;
  color: #0369a1;
  display: inline-block;
  font-size: 0.72rem;
  margin-right: 4px;
  padding: 1px 5px;
}
.side-by-side-diff .line-text {
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  white-space: pre-wrap;
  word-break: break-word;
}
.side-by-side-diff .diff-delete td:nth-child(1),
.side-by-side-diff .diff-delete td:nth-child(2) {
  background: #fee2e2;
}
.side-by-side-diff .diff-insert td:nth-child(3),
.side-by-side-diff .diff-insert td:nth-child(4) {
  background: #dcfce7;
}
.side-by-side-diff .diff-replace td {
  background: #fef3c7;
}
.side-by-side-diff .diff-equal td {
  background: #ffffff;
}
</style>
<div class="side-by-side-diff">
  <table>
    <thead>
      <tr>
        <th class="line-no">#</th>
        <th>V1 (cu)</th>
        <th class="line-no">#</th>
        <th>V2 (moi)</th>
      </tr>
    </thead>
    <tbody>
      __DIFF_ROWS__
    </tbody>
  </table>
</div>
""".replace("__DIFF_ROWS__", "\n".join(html_rows)),
        unsafe_allow_html=True,
    )


# ── Overview metrics ─────────────────────────────────────────────────

def render_metrics(report: dict):
    """Display top-level summary metrics."""
    cfg = report.get('config', {})
    status = cfg.get('status_counts', {})
    total = cfg.get('total_khoans') or cfg.get('total_articles', 0)

    changed = status.get('changed', 0)
    added = status.get('added', 0)
    removed = status.get('removed', 0)
    unchanged = status.get('unchanged', 0)

    cols = st.columns(4)
    cols[0].metric("Tong so Khoan", total)
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
        dieu = item.get('dieu_number') or item.get('article_number', '')
        khoan = item.get('khoan_number', '0')
        title = item.get('article_title', '')

        header = f"{icon} **[{label}]** Dieu {dieu}"
        if khoan and khoan != '0':
            header += f" · Khoan {khoan}"
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

            # Full side-by-side content
            if item.get('v1_text') or item.get('v2_text'):
                st.markdown("**Noi dung day du V1 / V2:**")
                render_side_by_side_diff(item)

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
        st.markdown(f"### {icon} {label} ({len(items)} khoan)")
        for item in items:
            dieu = item.get('dieu_number') or item.get('article_number', '')
            khoan = item.get('khoan_number', '0')
            ref = f"Dieu {dieu} · Khoan {khoan}" if khoan and khoan != '0' else f"Dieu {dieu}"
            conclusion = item.get('conclusion', '(khong co ket luan)')
            st.markdown(f"- **{ref}**: {conclusion}")


# ── 3. Citation / excerpt table ──────────────────────────────────────

def render_citations(comparison_results: list[dict]):
    """Render evidence excerpts with article location."""
    rows = []
    for item in comparison_results:
        if item['status'] == 'unchanged':
            continue
        if not item.get('evidence'):
            rows.append({
                'Dieu': item.get('dieu_number') or item.get('article_number', ''),
                'Khoan': item.get('khoan_number', '0'),
                'Trang thai': f"{STATUS_ICONS.get(item['status'],'')} {item['status']}",
                'Loai': '—',
                'Trich doan V1': '(khong co bang chung)',
                'Trich doan V2': '',
            })
            continue
        for ev in item['evidence']:
            rows.append({
                'Dieu': item.get('dieu_number') or item.get('article_number', ''),
                'Khoan': item.get('khoan_number', '0'),
                'Trang thai': f"{STATUS_ICONS.get(item['status'],'')} {item['status']}",
                'Loai': ev.get('tag', 'changed'),
                'Trich doan V1': ev.get('before', ''),
                'Trich doan V2': ev.get('after', ''),
            })

    if not rows:
        st.info("Khong co trich dan.")
        return

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ── 4. Full document side-by-side view ──────────────────────────────

_STATUS_BG = {
    'changed':   '#fef9c3',   # yellow-100
    'added':     '#dbeafe',   # blue-100
    'removed':   '#fee2e2',   # red-100
    'unchanged': '#ffffff',
}
_STATUS_BORDER = {
    'changed':   '#fbbf24',
    'added':     '#60a5fa',
    'removed':   '#f87171',
    'unchanged': '#e5e7eb',
}


def _doc_block(dieu: str, khoan: str, title: str, text: str, status: str, side: str) -> str:
    """Render one article/khoan block as an HTML card for the document view."""
    bg     = _STATUS_BG.get(status, '#ffffff')
    border = _STATUS_BORDER.get(status, '#e5e7eb')
    icon   = STATUS_ICONS.get(status, '')
    label  = STATUS_LABELS.get(status, status)

    khoan_badge = f'<span style="font-size:0.75rem;color:#64748b;">Khoản {khoan}</span>' if khoan and khoan != '0' else ''
    empty_note  = '<span style="color:#94a3b8;font-style:italic;">(không có nội dung)</span>' if not text else ''
    body        = html.escape(text).replace('\n', '<br>') if text else ''

    return (
        f'<div style="'
        f'background:{bg};border:1.5px solid {border};border-radius:8px;'
        f'padding:0.75rem 1rem;margin-bottom:0.6rem;'
        f'">'
        f'<div style="display:flex;align-items:baseline;gap:0.5rem;margin-bottom:0.35rem;">'
        f'<span style="font-weight:700;font-size:0.85rem;">Điều {dieu}</span>'
        f'{khoan_badge}'
        f'<span style="flex:1;font-size:0.8rem;color:#475569;">{html.escape(title)}</span>'
        f'<span style="font-size:0.72rem;color:#64748b;">{icon} {label}</span>'
        f'</div>'
        f'<div style="font-size:0.83rem;line-height:1.55;white-space:pre-wrap;word-break:break-word;">'
        f'{body}{empty_note}'
        f'</div>'
        f'</div>'
    )


def render_document_view(comparison_results: list[dict]):
    """Render full V1 and V2 documents side by side, colour-coded by change status."""
    import re as _re

    def _sort_key(item):
        def _num(s):
            m = _re.match(r'^(\d+)', str(s or '0'))
            return int(m.group(1)) if m else 0
        return (_num(item.get('dieu_number', 0)), _num(item.get('khoan_number', 0)))

    items = sorted(comparison_results, key=_sort_key)

    # Legend
    st.markdown(
        ' &nbsp; '.join(
            f'<span style="background:{_STATUS_BG[s]};border:1px solid {_STATUS_BORDER[s]};'
            f'border-radius:4px;padding:2px 8px;font-size:0.8rem;">'
            f'{STATUS_ICONS[s]} {STATUS_LABELS[s]}</span>'
            for s in ['changed', 'added', 'removed', 'unchanged']
        ),
        unsafe_allow_html=True,
    )
    st.markdown("<div style='margin-bottom:0.8rem'></div>", unsafe_allow_html=True)

    col_v1, col_v2 = st.columns(2, gap="small")

    v1_blocks, v2_blocks = [], []
    for item in items:
        dieu  = str(item.get('dieu_number') or item.get('article_number', ''))
        khoan = str(item.get('khoan_number', '0'))
        title = item.get('article_title', '')
        status = item.get('status', 'unchanged')

        v1_text = item.get('v1_text', '')
        v2_text = item.get('v2_text', '')

        # For added items V1 is empty; for removed items V2 is empty
        v1_status = 'removed' if status == 'added' else status
        v2_status = 'added'   if status == 'removed' else status

        v1_blocks.append(_doc_block(dieu, khoan, title, v1_text or '', v1_status, 'v1'))
        v2_blocks.append(_doc_block(dieu, khoan, title, v2_text or '', v2_status, 'v2'))

    scroll_style = (
        'height:72vh;overflow-y:auto;border:1px solid #e2e8f0;'
        'border-radius:10px;padding:0.8rem;background:#fafafa;'
    )

    with col_v1:
        st.markdown("**📄 V1 — Phiên bản cũ**")
        st.markdown(
            f'<div style="{scroll_style}">{"".join(v1_blocks)}</div>',
            unsafe_allow_html=True,
        )

    with col_v2:
        st.markdown("**📄 V2 — Phiên bản mới**")
        st.markdown(
            f'<div style="{scroll_style}">{"".join(v2_blocks)}</div>',
            unsafe_allow_html=True,
        )
