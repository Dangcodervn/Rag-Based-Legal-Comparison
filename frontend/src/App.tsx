import { useState, useEffect } from "react";
import type { CompareResponse, HealthStatus } from "./types";
import { checkHealth, compareDocuments } from "./api/client";
import StatusBanner from "./components/StatusBanner";
import CompareTab from "./components/CompareTab";
import SideBySideTab from "./components/SideBySideTab";

type Tab = "compare" | "parallel";

export default function App() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>("compare");
  const [result, setResult] = useState<CompareResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Poll health status every 8 seconds
  useEffect(() => {
    const poll = async () => {
      try {
        setHealth(await checkHealth());
      } catch {
        /* server not yet available */
      }
    };
    void poll();
    const id = setInterval(poll, 8000);
    return () => clearInterval(id);
  }, []);

  const handleCompare = async (fileV1: File, fileV2: File) => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await compareDocuments(fileV1, fileV2);
      setResult(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Lỗi không xác định");
    } finally {
      setIsLoading(false);
    }
  };

  const tabs: { id: Tab; label: string }[] = [
    { id: "compare", label: "📊 So sánh" },
    { id: "parallel", label: "📄 Văn bản Song song" },
  ];

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      <StatusBanner health={health} />

      <div className="flex-1 max-w-screen-2xl mx-auto w-full px-4 py-4">
        {/* Tab bar */}
        <div className="flex border-b border-slate-200 mb-4">
          {tabs.map(({ id, label }) => (
            <button
              key={id}
              onClick={() => setActiveTab(id)}
              className={`px-5 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                activeTab === id
                  ? "border-blue-600 text-blue-600"
                  : "border-transparent text-slate-500 hover:text-slate-700"
              }`}
            >
              {label}
            </button>
          ))}
        </div>

        {activeTab === "compare" && (
          <CompareTab
            onCompare={handleCompare}
            result={result}
            isLoading={isLoading}
            error={error}
          />
        )}
        {activeTab === "parallel" && <SideBySideTab result={result} />}
      </div>
    </div>
  );
}
