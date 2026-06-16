import type { ComparisonItem, ReportConfig } from "../types";

interface Props {
  config: ReportConfig;
  results: ComparisonItem[];
}

const STATUS_STYLES: Record<string, string> = {
  changed: "bg-amber-100 text-amber-800 border-amber-200",
  added: "bg-green-100 text-green-800 border-green-200",
  removed: "bg-red-100 text-red-800 border-red-200",
  unchanged: "bg-slate-100 text-slate-600 border-slate-200",
};
const STATUS_LABELS: Record<string, string> = {
  changed: "Sửa đổi",
  added: "Thêm mới",
  removed: "Xóa bỏ",
  unchanged: "Không đổi",
};

export default function MetricsSummary({ config, results }: Props) {
  const totalV1 = results.filter(
    (item) =>
      item.status === "changed" ||
      item.status === "unchanged" ||
      item.status === "removed",
  ).length;
  const totalV2 = results.filter(
    (item) =>
      item.status === "changed" ||
      item.status === "unchanged" ||
      item.status === "added",
  ).length;

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-4">
      <div className="text-xs text-slate-400 mb-3 flex gap-2 flex-wrap">
        <span className="font-medium text-slate-600">{config.file_v1}</span>
        <span>→</span>
        <span className="font-medium text-slate-600">{config.file_v2}</span>
      </div>
      <div className="flex flex-wrap gap-2">
        {Object.entries(STATUS_LABELS).map(([key, label]) => {
          const count = config.status_counts[key] ?? 0;
          return (
            <div
              key={key}
              className={`px-3 py-1.5 rounded-lg border text-sm font-medium ${STATUS_STYLES[key]}`}
            >
              {label}: <span className="font-bold">{count}</span>
            </div>
          );
        })}
        <div className="px-3 py-1.5 rounded-lg border border-blue-200 bg-blue-50 text-blue-700 text-sm font-medium">
          Tổng khoản V1: <span className="font-bold">{totalV1}</span>
        </div>
        <div className="px-3 py-1.5 rounded-lg border border-cyan-200 bg-cyan-50 text-cyan-700 text-sm font-medium">
          Tổng khoản V2: <span className="font-bold">{totalV2}</span>
        </div>
        <div className="px-3 py-1.5 rounded-lg border border-slate-200 bg-slate-50 text-slate-700 text-sm font-medium">
          Tổng dòng kết quả:{" "}
          <span className="font-bold">{config.total_khoans}</span>
        </div>
        <div className="px-3 py-1.5 rounded-lg border border-purple-200 bg-purple-50 text-purple-700 text-sm font-medium">
          LLM: <span className="font-bold">{config.llm_used_count}</span> |
          Grounded: <span className="font-bold">{config.grounded_count}</span>
        </div>
      </div>
    </div>
  );
}
