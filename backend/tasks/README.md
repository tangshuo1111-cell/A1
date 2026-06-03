# backend/tasks

## Responsibilities

- 承载异步控制平面，是系统的任务编排与状态控制层
- 统一任务提交、任务状态机、队列抽象、结果查询相关逻辑
- 为长任务和后台任务提供平台级承接面
- 与 `workers/` 协作，但不替代 worker runtime

## Boundary / What not to put here

- 不要把具体业务能力实现放进 `tasks/`
- 不要把 HTTP 路由、前端返回格式判断放进 `tasks/`
- 不要把长期驻留的消费循环和线程池逻辑放在这里，那些属于 `workers/`
- 不要让视频专项临时实现永远停留在根目录，后续应收敛到 `queue/` 与 `orchestration/`

## Owned files

- `backend/tasks/task_runner.py`
- `backend/tasks/task_store.py`
- `backend/tasks/video_task_queue.py`
- 未来预留：
  - `backend/tasks/queue/`
  - `backend/tasks/orchestration/`

## Files that must not keep growing

- `backend/tasks/video_task_queue.py`
  当前是视频专项队列抽象，后续应迁入 `tasks/queue/`，不应继续变成平台内所有任务逻辑的单文件聚集点。
- `backend/tasks/task_runner.py`
  应聚焦任务编排，不应继续吸收 worker 行为与能力细节。
- `backend/tasks/task_store.py`
  应聚焦任务状态与存取，不应吸收 API 或业务能力分支判断。
