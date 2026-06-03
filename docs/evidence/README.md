# 验收证据包（不进主线）

V16「真实验收证据包」正文已从仓库主线移除，以降低 `git clone` 体量（目标：**纯仓库 clone** 体积约小于 50MB；删除后与远端 gc 后以实测为准）。

## 去哪里拿

- **GitHub Releases**：维护者将原先目录 **`V16_真实验收证据包/`**（整文件夹）打成 **`V16_真实验收证据包.zip`**，上传到**本仓库**的 Release（Assets）。
- **链接占位**：  
  `https://github.com/<OWNER>/<REPO>/releases/download/<TAG>/V16_真实验收证据包.zip`  
  （替换为实际的 `OWNER`、`REPO`、`TAG`。）

## 为什么这样放

- Release 附件长期可用；日常 `clone` 不拉大文件  
- 不占主线历史  
- 与治理口径「主线只保留 README 外链」一致
