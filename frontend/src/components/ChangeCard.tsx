import { useState } from "react";
import type { ComparisonItem } from "../types";

const STATUS_STYLES: Record<string, { badge: string; border: string }> = {
  changed: {
    badge: "bg-amber-100 text-amber-800",
    border: "border-l-amber-400",
  },
  added: { badge: "bg-green-100 text-green-800", border: "border-l-green-500" },
  removed: { badge: "bg-red-100 text-red-800", border: "border-l-red-400" },
  unchanged: {
    badge: "bg-slate-100 text-slate-600",
    border: "border-l-slate-300",
  },
};
const STATUS_LABELS: Record<string, string> = {
  changed: "Sửa đổi",
  added: "Thêm mới",
  removed: "Xóa bỏ",
  unchanged: "Không đổi",
};
const EVIDENCE_COLORS: Record<string, string> = {
  changed: "bg-amber-50 text-amber-800",
  added: "bg-green-50 text-green-800",
  removed: "bg-red-50 text-red-800",
};
const EVIDENCE_TAG_LABELS: Record<string, string> = {
  changed: "Thay đổi",
  added: "Thêm vào",
  removed: "Xóa bỏ",
};

interface Props {
  item: ComparisonItem;
}

export default function ChangeCard({ item }: Props) {
  const [expanded, setExpanded] = useState(false);
  const style = STATUS_STYLES[item.status] ?? STATUS_STYLES.unchanged;
  const hasEvidence = item.evidence.length > 0;
  const isSignificant = item.status !== "unchanged";

  return (
    <div
      className={`bg-white rounded-lg border border-slate-200 border-l-4 ${style.border} shadow-sm`}
    >
      {/* Header row */}
      <div className="px-4 py-3 flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span
              className={`px-2 py-0.5 rounded text-xs font-semibold ${style.badge}`}
            >
              {STATUS_LABELS[item.status] ?? item.status}
            </span>

            {/* V1 location — only items that actually exist in V1 */}
            {!item.v2_only && (
              <span className="inline-flex items-center gap-1">
                <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-blue-100 text-blue-700 leading-none">
                  V1
                </span>
                <span className="text-sm font-semibold text-slate-700">
                  Điều {item.dieu_number ?? item.article_number}
                  {item.khoan_number && item.khoan_number !== "0"
                    ? ` – Khoản ${item.khoan_number}`
                    : ""}
                </span>
              </span>
            )}

            {/* V2 location */}
            {item.status !== "removed" &&
              item.matched_article_v2 &&
              (() => {
                // For v2_only items, dieu_number/khoan_number ARE the V2 coords.
                // For matched items, parse from matched_article_v2.
                let v2Dieu: string;
                let v2Khoan: string | null;
                if (item.v2_only) {
                  v2Dieu = item.dieu_number ?? item.article_number;
                  v2Khoan =
                    item.khoan_number && item.khoan_number !== "0"
                      ? item.khoan_number
                      : null;
                } else {
                  const v2Parts = item.matched_article_v2.split(".");
                  v2Dieu = v2Parts[0];
                  v2Khoan =
                    v2Parts.length > 1 ? v2Parts.slice(1).join(".") : null;
                }
                return (
                  <>
                    {!item.v2_only && (
                      <span className="text-slate-400 text-xs">→</span>
                    )}
                    <span className="inline-flex items-center gap-1">
                      <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-orange-100 text-orange-700 leading-none">
                        V2
                      </span>
                      <span className="text-sm font-semibold text-slate-500">
                        Điều {v2Dieu}
                        {v2Khoan ? ` – Khoản ${v2Khoan}` : ""}
                      </span>
                    </span>
                  </>
                );
              })()}

            {item.article_title && (
              <span className="text-sm text-slate-500 truncate">
                {item.article_title}
              </span>
            )}
          </div>

          {item.conclusion && (
            <p className="mt-1.5 text-sm text-slate-600 leading-snug">
              {item.conclusion}
            </p>
          )}

          <div className="mt-1.5 flex items-center gap-3 text-xs text-slate-400">
            <span>Tương đồng: {(item.match_score * 100).toFixed(0)}%</span>
            {item.grounded && (
              <span className="text-green-600">✓ Có bằng chứng</span>
            )}
            {!item.grounded && isSignificant && (
              <span className="text-amber-500">⚠ Chưa có bằng chứng</span>
            )}
          </div>
        </div>

        {hasEvidence && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-xs text-blue-600 hover:text-blue-800 flex-shrink-0 mt-0.5 whitespace-nowrap"
          >
            {expanded ? "▲ Ẩn" : `▼ ${item.evidence.length} bằng chứng`}
          </button>
        )}
      </div>

      {/* Evidence detail */}
      {expanded && hasEvidence && (
        <div className="border-t border-slate-100 px-4 py-3 space-y-2">
          {item.evidence.map((ev, idx) => (
            <div
              key={idx}
              className={`rounded p-2 text-xs ${EVIDENCE_COLORS[ev.tag] ?? "bg-slate-50 text-slate-700"}`}
            >
              <span className="font-semibold mr-2">
                [{EVIDENCE_TAG_LABELS[ev.tag] ?? ev.tag}]
              </span>
              {ev.before && (
                <>
                  <span className="line-through text-red-500 mr-1">
                    {ev.before}
                  </span>
                  {ev.after && (
                    <span className="text-green-700">{ev.after}</span>
                  )}
                </>
              )}
              {!ev.before && ev.after && (
                <span className="text-green-700">{ev.after}</span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
