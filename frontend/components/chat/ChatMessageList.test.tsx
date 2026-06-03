import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { ChatMessage } from "@/lib/types";

import { ChatMessageList } from "./ChatMessageList";

describe("ChatMessageList", () => {

  it("渲染用户与助手消息", () => {
    const messages: ChatMessage[] = [
      { id: "1", role: "user", content: "你好" },
      { id: "2", role: "assistant", content: "收到" },
    ];
    render(<ChatMessageList messages={messages} isGenerating={false} generatingSince={null} />);
    expect(screen.getByText("你好")).toBeDefined();
    expect(screen.getByText("收到")).toBeDefined();
  });

  it("助手气泡经 sanitizeAssistantAnswer 去掉标记片段", () => {
    const messages: ChatMessage[] = [
      {
        id: "a1",
        role: "assistant",
        content: "说明[doc_path]结束",
      },
    ];
    render(<ChatMessageList messages={messages} isGenerating={false} generatingSince={null} />);
    expect(screen.getByText("说明结束")).toBeDefined();
    expect(screen.queryByText(/\[doc_path\]/)).toBeNull();
  });

  it("生成中显示占位提示", () => {
    render(<ChatMessageList messages={[]} isGenerating generatingSince={Date.now()} />);
    expect(screen.getByText("正在整理回复")).toBeDefined();
  });
});
