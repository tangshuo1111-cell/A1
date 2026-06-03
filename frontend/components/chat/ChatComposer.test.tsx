import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ChatComposer } from "./ChatComposer";

describe("ChatComposer", () => {
  it("暴露可访问的输入与发送控件", () => {
    render(
      <ChatComposer
        value=""
        onChange={vi.fn()}
        onSubmit={vi.fn()}
        disabled={false}
      />,
    );
    expect(screen.getByRole("textbox", { name: /message input/i })).toBeDefined();
    expect(screen.getByRole("button", { name: /send/i })).toBeDefined();
  });

  it("有内容且未禁用时 Enter（非 Shift）触发 onSubmit", () => {
    const onSubmit = vi.fn();
    render(
      <ChatComposer
        value="hi"
        onChange={vi.fn()}
        onSubmit={onSubmit}
        disabled={false}
      />,
    );
    const input = screen.getByRole("textbox", { name: /message input/i });
    fireEvent.keyDown(input, { key: "Enter", shiftKey: false });
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it("内容为空时发送按钮不可用", () => {
    render(
      <ChatComposer
        value="  "
        onChange={vi.fn()}
        onSubmit={vi.fn()}
        disabled={false}
      />,
    );
    const send = screen.getByRole("button", { name: /send/i }) as HTMLButtonElement;
    expect(send.disabled).toBe(true);
  });
});
