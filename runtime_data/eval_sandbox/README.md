# Eval Sandbox

本目录用于保存评测运行时沙盒产物。

用途包括：

- 临时上传文件
- 临时 task 结果
- 临时 KB seed
- 评测报告
- trace
- 临时文件

本目录不用于：

- 保存正式业务数据
- 保存真实用户上传
- 保存真实 cookie / key
- 保存正式知识库内容

默认只提交：

- 本 README
- 各子目录 `.gitkeep`

运行期产物应写入以下子目录：

- `uploads/`
- `task_results/`
- `kb_seed/`
- `reports/`
- `traces/`
- `tmp/`
