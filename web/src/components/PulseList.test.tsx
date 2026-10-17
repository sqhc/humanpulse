import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { messages } from "../i18n";
import { PulseList } from "./PulseList";

const ZH_PULSE = {
  section_key: "conflict",
  fact_zh: "泽连斯基称俄方未理会停火呼吁（卫报）",
  fact_en: "Zelensky says Russia ignored ceasefire call (Guardian)",
  hook_zh: "停火调停连续落空，谈判筹码还没摆上桌。",
  hook_en: "Mediation keeps failing; leverage is not yet on the table.",
  source_name: "卫报",
};

describe("PulseList", () => {
  it("渲染事实与钩子，带主题标签", () => {
    render(<PulseList pulses={[ZH_PULSE]} lang="zh" t={messages.zh} />);

    expect(screen.getByTestId("pulse-list")).toBeInTheDocument();
    expect(screen.getByText(ZH_PULSE.fact_zh)).toBeInTheDocument();
    expect(screen.getByText(ZH_PULSE.hook_zh)).toBeInTheDocument();
    expect(screen.getByText("冲突")).toBeInTheDocument();
  });

  it("钩子缺失时只渲染事实，不编造「为什么重要」", () => {
    render(
      <PulseList
        pulses={[{ ...ZH_PULSE, hook_zh: "", hook_en: "" }]}
        lang="zh"
        t={messages.zh}
      />,
    );

    expect(screen.getByText(ZH_PULSE.fact_zh)).toBeInTheDocument();
    expect(screen.queryByText("→")).toBeNull();
  });

  it("空列表（旧简报没有 pulses 字段）时不渲染任何内容", () => {
    const { container } = render(<PulseList pulses={[]} lang="zh" t={messages.zh} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("英文语言取英文事实", () => {
    render(<PulseList pulses={[ZH_PULSE]} lang="en" t={messages.en} />);
    expect(screen.getByText(ZH_PULSE.fact_en)).toBeInTheDocument();
  });
});
