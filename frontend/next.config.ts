import type { NextConfig } from "next";

/**
 * Next.js 构建配置（基础设施层）。
 *
 * V17：`/api-proxy/*` 不再使用 rewrite，而是由 app router 下的
 * `app/api-proxy/[...path]/route.ts` 显式代理到后端。
 * 这样可以更稳定地处理较慢请求，并把后端错误体原样透传给浏览器。
 */
const nextConfig: NextConfig = {};

export default nextConfig;
