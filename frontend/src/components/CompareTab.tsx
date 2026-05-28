import { useState, useMemo } from "react";
import type { CompareResponse, ChangeStatus, ComparisonItem } from "../types";
import UploadPanel from "./UploadPanel";
import MetricsSummary from "./MetricsSummary";
import ChangeCard from "./ChangeCard";

type FilterStatus = "all" | ChangeStatus;

const FILTERS: { value: FilterStatus; label: string }[] = [
  { value: "all", label: "Tất cả" },
  { value: "changed", label: "Sửa đổi" },
  { value: "added", label: "Thêm mới" },
  { value: "removed", label: "Xóa bỏ" },
  { value: "unchanged", label: "Không đổi" },
];

/** Sort by điều number, then khoản number — numerically */
function sortByArticle(items: ComparisonItem[]): ComparisonItem[] {
  return [...items].sort((a, b) => {
    const dA = parseFloat(a.dieu_number ?? a.article_number) || 0;
    const dB = parseFloat(b.dieu_number ?? b.article_number) || 0;
    if (dA !== dB) return dA - dB;
    const kA = parseFloat(a.khoan_number ?? "0") || 0;
    const kB = parseFloat(b.khoan_number ?? "0") || 0;
    return kA - kB;
  });
}

interface Props {
  onCompare: (v1: File, v2: File) => void;
  result: CompareResponse | null;
  isLoading: boolean;
  error: string | null;
}

export default function CompareTab({
  onCompare,
  result,
  isLoading,
  error,
}: Props) {
  const [filter, setFilter] = useState<FilterStatus>("all");

  const filtered = useMemo(
    () =>
      result
        ? sortByArticle(
            filter === "all"
              ? result.results
              : result.results.filter((r) => r.status === filter),
          )
        : [],
    [result, filter],
  );

  return (
    <div className="space-y-4">
      <UploadPanel onCompare={onCompare} isLoading={isLoading} />

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 rounded-lg px-4 py-3 text-sm">
          ❌ {error}
        </div>
      )}

      {isLoading && (
        <div className="bg-blue-50 border border-blue-200 text-blue-700 rounded-lg px-4 py-8 text-sm text-center">
          <div className="text-2xl mb-2 animate-pulse">⏳</div>
          Đang so sánh tài liệu… Quá trình này có thể mất vài phút.
        </div>
      )}

      {result && !isLoading && (
        <>
          <MetricsSummary config={result.config} />

          {/* Filter bar */}
          <div className="flex items-center gap-2 flex-wrap">
            {FILTERS.map(({ value, label }) => {
              const count =
                value === "all"
                  ? result.results.length
                  : result.results.filter((r) => r.status === value).length;
              return (
                <button
                  key={value}
                  onClick={() => setFilter(value)}
                  className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                    filter === value
                      ? "bg-blue-600 text-white"
                      : "bg-white border border-slate-200 text-slate-600 hover:bg-slate-50"
                  }`}
                >
                  {label} ({count})
                </button>
              );
            })}
          </div>

          {/* Results list */}
          <div className="space-y-2">
            {filtered.length === 0 ? (
              <div className="text-center py-10 text-slate-400 text-sm">
                Không có kết quả cho bộ lọc này.
              </div>
            ) : (
              filtered.map((item, idx) => <ChangeCard key={idx} item={item} />)
            )}
          </div>
        </>
      )}

      {!result && !isLoading && !error && (
        <div className="text-center py-14 text-slate-400 text-sm">
          ⬆️ Tải lên 2 tài liệu và nhấn <strong>So sánh</strong> để bắt đầu.
        </div>
      )}
    </div>
  );
}
