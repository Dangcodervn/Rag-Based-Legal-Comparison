import { useEffect, useRef, useState } from "react";
import { renderAsync } from "docx-preview";

// Vietnamese font substitution: map legacy VN font names to web-safe equivalents.
// docx-preview injects a <style> that references font-family names from the DOCX;
// these overrides ensure unresolvable fonts fall back gracefully.
const DOCX_STYLE = `
  /* Improve text rendering in all docx-preview containers */
  .docx-wrapper, .docx-wrapper * {
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    text-rendering: optimizeLegibility;
  }
  /* Legacy Vietnamese font substitution */
  @font-face { font-family: ".VnTime";       src: local("Times New Roman"); }
  @font-face { font-family: ".VnArial";      src: local("Arial"); }
  @font-face { font-family: "VNI-Times";     src: local("Times New Roman"); }
  @font-face { font-family: "VNI-Arial";     src: local("Arial"); }
  @font-face { font-family: ".VnTimesH";     src: local("Times New Roman"); }
  @font-face { font-family: "SVN-Times New Roman"; src: local("Times New Roman"); }
  @font-face { font-family: "Times New Roman CE";  src: local("Times New Roman"); }
`;

interface Props {
  url: string | null;
  title: string;
}

type Status = "idle" | "loading" | "done" | "error";

export default function DocViewer({ url, title }: Props) {
  const bodyRef = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [errMsg, setErrMsg] = useState("");

  // Inject shared DOCX styles once
  useEffect(() => {
    const id = "docx-global-style";
    if (!document.getElementById(id)) {
      const el = document.createElement("style");
      el.id = id;
      el.textContent = DOCX_STYLE;
      document.head.appendChild(el);
    }
  }, []);

  useEffect(() => {
    if (!url) {
      setStatus("idle");
      return;
    }
    const container = bodyRef.current;
    if (!container) return;

    container.innerHTML = "";
    setStatus("loading");
    setErrMsg("");

    fetch(url)
      .then((r) => {
        if (!r.ok)
          throw new Error(`HTTP ${r.status} — tài liệu không tải được`);
        return r.arrayBuffer();
      })
      .then((buf) =>
        renderAsync(buf, container, undefined, {
          inWrapper: true,
          ignoreWidth: false,
          ignoreHeight: false,
          ignoreFonts: false,
          useBase64URL: true,
        }),
      )
      .then(() => setStatus("done"))
      .catch((e: Error) => {
        setErrMsg(e.message ?? "Lỗi không xác định");
        setStatus("error");
      });
  }, [url]);

  return (
    <div className="flex flex-col h-full border border-slate-200 rounded-xl overflow-hidden bg-white shadow-sm">
      {/* Header */}
      <div className="bg-slate-100 border-b border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 flex-shrink-0 truncate">
        📄 {title}
      </div>

      {/* Body */}
      <div className="flex-1 overflow-auto relative bg-gray-50">
        {!url && (
          <div className="absolute inset-0 flex items-center justify-center text-slate-400 text-sm">
            Tài liệu không khả dụng
          </div>
        )}
        {status === "loading" && (
          <div className="absolute inset-0 flex items-center justify-center text-slate-500 text-sm animate-pulse bg-gray-50">
            ⏳ Đang tải tài liệu…
          </div>
        )}
        {status === "error" && (
          <div className="absolute inset-0 flex items-center justify-center text-red-500 text-sm px-6 text-center">
            ❌ {errMsg}
          </div>
        )}

        {/* docx-preview renders here */}
        <div ref={bodyRef} className={status === "done" ? "" : "hidden"} />
      </div>
    </div>
  );
}
