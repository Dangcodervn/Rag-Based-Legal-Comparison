import type { CompareResponse } from "../types";
import DocViewer from "./DocViewer";
import { docxUrl } from "../api/client";

interface Props {
  result: CompareResponse | null;
}

export default function SideBySideTab({ result }: Props) {
  if (!result) {
    return (
      <div className="text-center py-14 text-slate-400 text-sm">
        ⬆️ Tải lên cả 2 file ở tab <strong>So sánh</strong> để xem văn bản gốc
        song song.
      </div>
    );
  }

  const urlV1 = result.has_docx_v1 ? docxUrl(result.session_id, "v1") : null;
  const urlV2 = result.has_docx_v2 ? docxUrl(result.session_id, "v2") : null;

  return (
    <div className="flex gap-3" style={{ height: "calc(100vh - 160px)" }}>
      <div className="flex-1 min-w-0 h-full">
        <DocViewer url={urlV1} title={result.config.file_v1} />
      </div>
      <div className="flex-1 min-w-0 h-full">
        <DocViewer url={urlV2} title={result.config.file_v2} />
      </div>
    </div>
  );
}
