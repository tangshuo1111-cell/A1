/**
 * 应用首页：挂载聊天主体验（App Router 页面层）。
 * 业务 UI 在 components/chat/ChatExperience。
 */

import { ChatExperience } from "@/components/chat/ChatExperience";

export default function Home() {
  return <ChatExperience />;
}
