import { useEffect, useRef, useState } from "react";
import { ChevronLeftIcon, ChevronRightIcon, LoaderIcon } from "lucide-react";
import {
  getDocument,
  GlobalWorkerOptions,
  type PDFDocumentProxy,
} from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { Button } from "@/components/ui/button";

GlobalWorkerOptions.workerSrc = workerUrl;

export default function PdfPreview({ url }: { url: string }) {
  const [document, setDocument] = useState<PDFDocumentProxy | null>(null);
  const [pageNumber, setPageNumber] = useState(1);
  const [width, setWidth] = useState(500);
  const [error, setError] = useState("");
  const [rendering, setRendering] = useState(false);
  const container = useRef<HTMLDivElement>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    setError("");
    setDocument(null);
    setPageNumber(1);
    let active = true;
    const loading = getDocument({ url });
    loading.promise
      .then((pdf) => {
        if (active) setDocument(pdf);
      })
      .catch(() => {
        if (active) setError("排版预览暂不可用，请下载 Word 或 PDF 查看。");
      });
    return () => {
      active = false;
      void loading.destroy();
    };
  }, [url]);
  useEffect(() => {
    if (!container.current) return;
    const observer = new ResizeObserver(([entry]) => {
      if (entry.contentRect.width > 0)
        setWidth(Math.max(120, entry.contentRect.width - 32));
    });
    observer.observe(container.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (!document || !canvas.current) return;
    let disposed = false;
    let render:
      | ReturnType<Awaited<ReturnType<PDFDocumentProxy["getPage"]>>["render"]>
      | undefined;
    setRendering(true);
    document
      .getPage(pageNumber)
      .then((page) => {
        if (disposed || !canvas.current) return;
        const element = canvas.current;
        const ratio = Math.min(window.devicePixelRatio || 1, 2);
        const viewport = page.getViewport({
          scale: width / page.getViewport({ scale: 1 }).width,
        });
        element.width = Math.floor(viewport.width * ratio);
        element.height = Math.floor(viewport.height * ratio);
        element.style.width = `${viewport.width}px`;
        element.style.height = `${viewport.height}px`;
        render = page.render({
          canvas: element,
          viewport,
          transform: ratio === 1 ? undefined : [ratio, 0, 0, ratio, 0, 0],
        });
        return render.promise;
      })
      .then(() => {
        if (!disposed) setRendering(false);
      })
      .catch((e) => {
        if (!disposed && e?.name !== "RenderingCancelledException") {
          setRendering(false);
          setError("此页暂时无法渲染，请下载文件查看。");
        }
      });
    return () => {
      disposed = true;
      render?.cancel();
    };
  }, [document, pageNumber, width]);
  return (
    <div ref={container} className="flex h-full min-h-0 flex-col bg-muted/40">
      {error ? (
        <p role="alert" className="m-4 text-sm leading-6 text-destructive">
          {error}
        </p>
      ) : (
        <>
          <div className="bg-background/80 flex h-10 shrink-0 items-center justify-center gap-3 border-b text-xs text-muted-foreground">
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="上一页"
              disabled={!document || pageNumber <= 1}
              onClick={() => setPageNumber((n) => n - 1)}
            >
              <ChevronLeftIcon />
            </Button>
            <span aria-live="polite">
              {document
                ? `${pageNumber} / ${document.numPages} 页`
                : "正在读取 PDF…"}
            </span>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label="下一页"
              disabled={!document || pageNumber >= document.numPages}
              onClick={() => setPageNumber((n) => n + 1)}
            >
              <ChevronRightIcon />
            </Button>
          </div>
          <div className="relative min-h-0 flex-1 overflow-auto p-4">
            {(!document || rendering) && (
              <div
                role="status"
                className="absolute top-6 left-1/2 z-10 -translate-x-1/2 rounded-full bg-background/90 px-3 py-2 text-xs shadow-sm"
              >
                <LoaderIcon className="inline-block size-3 animate-spin" />{" "}
                正在渲染排版
              </div>
            )}
            <canvas
              ref={canvas}
              aria-label={`周报 PDF 第 ${pageNumber} 页`}
              className="mx-auto max-w-full bg-white shadow-sm"
            />
          </div>
        </>
      )}
    </div>
  );
}
