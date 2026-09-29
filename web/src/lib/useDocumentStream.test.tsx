import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useDocumentStream } from "./useDocumentStream";

class FakeEventSource {
  static instances: FakeEventSource[] = [];
  url: string;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  private listeners = new Map<string, ((event: MessageEvent<string>) => void)[]>();

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, handler: (event: MessageEvent<string>) => void) {
    const list = this.listeners.get(type) ?? [];
    list.push(handler);
    this.listeners.set(type, list);
  }

  removeEventListener(type: string, handler: (event: MessageEvent<string>) => void) {
    const list = this.listeners.get(type) ?? [];
    this.listeners.set(
      type,
      list.filter((item) => item !== handler),
    );
  }

  emit(type: string, data: unknown) {
    for (const handler of this.listeners.get(type) ?? []) {
      handler({ data: JSON.stringify(data) } as MessageEvent<string>);
    }
  }

  close() {
    this.closed = true;
  }
}

function Probe({ onDocument }: { onDocument: (doc: unknown) => void }) {
  const { status, received } = useDocumentStream(onDocument as never);
  return (
    <div>
      <span data-testid="status">{status}</span>
      <span data-testid="received">{received}</span>
    </div>
  );
}

afterEach(() => {
  FakeEventSource.instances = [];
  vi.unstubAllGlobals();
});

describe("useDocumentStream", () => {
  it("连接 /api/v1/stream 并在 open 后标记为已连接", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    render(<Probe onDocument={() => undefined} />);

    const source = FakeEventSource.instances[0];
    expect(source.url).toBe("/api/v1/stream");
    source.onopen?.();

    await waitFor(() => expect(screen.getByTestId("status").textContent).toBe("open"));
  });

  it("收到 document 事件时回调并把计数加一", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const seen: unknown[] = [];
    render(<Probe onDocument={(doc) => seen.push(doc)} />);

    FakeEventSource.instances[0].emit("document", { id: 42, title: "新条目" });

    await waitFor(() => expect(screen.getByTestId("received").textContent).toBe("1"));
    expect(seen).toEqual([{ id: 42, title: "新条目" }]);
  });

  it("坏帧不影响后续事件", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const seen: unknown[] = [];
    render(<Probe onDocument={(doc) => seen.push(doc)} />);

    const source = FakeEventSource.instances[0];
    for (const handler of (source as unknown as { listeners: Map<string, ((e: MessageEvent<string>) => void)[]> }).listeners.get("document") ?? []) {
      handler({ data: "not-json" } as MessageEvent<string>);
    }
    source.emit("document", { id: 1 });

    await waitFor(() => expect(screen.getByTestId("received").textContent).toBe("1"));
  });

  it("卸载时关闭连接", () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const view = render(<Probe onDocument={() => undefined} />);
    const source = FakeEventSource.instances[0];
    view.unmount();
    expect(source.closed).toBe(true);
  });
});
