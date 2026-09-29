import { useEffect, useRef, useState } from "react";

export type StreamStatus = "connecting" | "open" | "closed";

export interface StreamedDocument {
  id: number;
  title: string;
  url: string;
  source_name: string | null;
  language: string | null;
  kind: string;
  published_at: string | null;
  fetched_at: string | null;
  score: number | null;
  summary_zh: string | null;
  summary_en: string | null;
  tags: string[];
  cluster_id: number | null;
}

/**
 * 订阅 `/api/v1/stream`（SSE）。事件到达时回调；返回连接状态与已收条数。
 *
 * 服务端默认从"当前最新一条之后"开始推，因此页面刷新不会补推历史（历史走 Feed 接口）。
 */
export function useDocumentStream(
  onDocument: (doc: StreamedDocument) => void,
): { status: StreamStatus; received: number } {
  // 没有 EventSource（SSR / 测试环境）时直接视为已断开，避免在 effect 里同步 setState
  const [status, setStatus] = useState<StreamStatus>(() =>
    typeof EventSource === "undefined" ? "closed" : "connecting",
  );
  const [received, setReceived] = useState(0);
  const callbackRef = useRef(onDocument);

  // 回调放进 effect 更新，避免"渲染期间写 ref"（React 19 的 lint 规则会报错）
  useEffect(() => {
    callbackRef.current = onDocument;
  }, [onDocument]);

  useEffect(() => {
    if (typeof EventSource === "undefined") {
      return;
    }
    const base = import.meta.env.VITE_API_BASE_URL ?? "";
    const source = new EventSource(`${base}/api/v1/stream`);
    source.onopen = () => setStatus("open");
    source.onerror = () => setStatus("closed");
    const handle = (event: MessageEvent<string>) => {
      try {
        const payload = JSON.parse(event.data) as StreamedDocument;
        callbackRef.current(payload);
        setReceived((count) => count + 1);
      } catch {
        // 坏帧忽略：流不能因为一条解析失败就断掉
      }
    };
    source.addEventListener("document", handle as EventListener);
    return () => {
      source.removeEventListener("document", handle as EventListener);
      source.close();
    };
  }, []);

  return { status, received };
}
