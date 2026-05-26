import type { HealthStatus } from "../types";

interface Props {
  health: HealthStatus | null;
}

function Dot({ ok }: { ok: boolean }) {
  return (
    <span
      className={`inline-block w-2 h-2 rounded-full mr-1.5 ${ok ? "bg-green-400" : "bg-red-400"}`}
    />
  );
}

export default function StatusBanner({ health }: Props) {
  if (!health) {
    return (
      <div className="bg-amber-50 border-b border-amber-200 px-4 py-2 text-sm text-amber-700">
        ⏳ Đang kết nối server…
      </div>
    );
  }

  const embedReady = health.embedder === "ready";
  const ollamaReady = health.ollama === "ready";

  return (
    <div className="bg-slate-800 border-b border-slate-700 px-4 py-2 flex items-center gap-6 text-sm text-slate-200">
      <span className="font-semibold text-white">⚖️ So sánh Pháp lý</span>
      <div className="flex items-center gap-5 ml-auto">
        <span className="flex items-center">
          <Dot ok={embedReady} />
          Embedding:{" "}
          <span
            className={`ml-1 font-medium ${embedReady ? "text-green-400" : "text-amber-400"}`}
          >
            {embedReady ? "Sẵn sàng" : "Đang tải…"}
          </span>
        </span>
        <span className="flex items-center">
          <Dot ok={ollamaReady} />
          Ollama:{" "}
          <span
            className={`ml-1 font-medium ${ollamaReady ? "text-green-400" : "text-red-400"}`}
          >
            {ollamaReady ? "Sẵn sàng" : "Không kết nối"}
          </span>
        </span>
      </div>
    </div>
  );
}
