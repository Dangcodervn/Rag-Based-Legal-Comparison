interface Props {
  url: string | null;
  title: string;
}

export default function DocViewer({ url, title }: Props) {
  return (
    <div className="flex flex-col h-full border border-slate-200 rounded-xl overflow-hidden bg-white shadow-sm">
      <div className="bg-slate-100 border-b border-slate-200 px-4 py-2 text-sm font-semibold text-slate-700 flex-shrink-0 truncate">
        📄 {title}
      </div>
      <div className="flex-1 overflow-hidden">
        {url ? (
          <iframe src={url} className="w-full h-full border-0" title={title} />
        ) : (
          <div className="flex items-center justify-center h-full text-slate-400 text-sm">
            PDF không khả dụng cho tài liệu này
          </div>
        )}
      </div>
    </div>
  );
}
