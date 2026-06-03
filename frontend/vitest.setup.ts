/** Vitest浏览器环境补齐与 RTL 生命周期 */
import { configure, cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

configure({
  reactStrictMode: false,
});

HTMLElement.prototype.scrollIntoView ??= vi.fn() as typeof HTMLElement.prototype.scrollIntoView;

afterEach(() => {
  cleanup();
});
