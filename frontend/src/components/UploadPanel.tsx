import { useRef, useState } from "react";

function FileDropZone({
  label,
  file,
  onChange,
}: {
  label: string;
  file: File | null;
  onChange: (f: File) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  return (
    <div
      className="border-2 border-dashed border-slate-300 rounded-lg p-6 text-center cursor-pointer
                 hover:border-blue-400 hover:bg-blue-50 transition-colors"
      onClick={() => inputRef.current?.click()}
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        e.preventDefault();
        const f = e.dataTransfer.files[0];
        if (f) onChange(f);
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".docx,.pdf"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) onChange(f);
        }}
      />
      <div className="text-2xl mb-1">📄</div>
      <div className="text-sm font-medium text-slate-600">{label}</div>
      {file ? (
        <div className="mt-1.5 text-xs text-blue-600 font-medium truncate max-w-full px-2">
          {file.name}
        </div>
      ) : (
        <div className="mt-1 text-xs text-slate-400">DOCX hoặc PDF</div>
      )}
    </div>
  );
}

interface Props {
  onCompare: (v1: File, v2: File) => void;
  isLoading: boolean;
}

export default function UploadPanel({ onCompare, isLoading }: Props) {
  const [fileV1, setFileV1] = useState<File | null>(null);
  const [fileV2, setFileV2] = useState<File | null>(null);

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-5">
      <h2 className="text-sm font-semibold text-slate-700 mb-4">
        📂 Tải lên tài liệu
      </h2>
      <div className="grid grid-cols-2 gap-4 mb-4">
        <div>
          <div className="text-xs font-medium text-slate-500 mb-1.5">
            Phiên bản 1 (gốc)
          </div>
          <FileDropZone
            label="Kéo thả hoặc click để chọn V1"
            file={fileV1}
            onChange={setFileV1}
          />
        </div>
        <div>
          <div className="text-xs font-medium text-slate-500 mb-1.5">
            Phiên bản 2 (sửa đổi)
          </div>
          <FileDropZone
            label="Kéo thả hoặc click để chọn V2"
            file={fileV2}
            onChange={setFileV2}
          />
        </div>
      </div>
      <button
        disabled={!fileV1 || !fileV2 || isLoading}
        onClick={() => fileV1 && fileV2 && onCompare(fileV1, fileV2)}
        className="w-full py-2.5 px-4 bg-blue-600 text-white text-sm font-semibold rounded-lg
                   hover:bg-blue-700 disabled:bg-slate-300 disabled:cursor-not-allowed transition-colors"
      >
        {isLoading ? "⏳ Đang so sánh…" : "🔍 So sánh"}
      </button>
    </div>
  );
}
