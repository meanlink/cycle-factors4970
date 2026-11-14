# 共享单车调度因子研究

偏相关与滞后相关的真实业务分析小型项目。完整模拟客户、痛点、上下游、算法公式与一天工作剧本见 [BUSINESS.md](BUSINESS.md)。

## 模块与业务流程
数据接入（JSON/CSV、观测日期、字段验证、批次指纹）→ 按日期组合批次（同键去重、冲突选源、版本快照）→ 参数化分析（异步 Python worker）→ 结果复核（指标、图形、明细、解释、批准）→ 定时分发（本地收件箱、CSV/JSON、SHA256）；另有业务总览和审计轨迹。
贯穿全栈的实体：Dataset 数据批次、Combination/CombinationVersion 日期组合与版本、Job 分析任务、Report 分发计划；辅助 User、Audit、Delivery。

### 按日期组合批次
- 组合由若干不可变批次组成，按 `observation_date` 合并；同一站点、同一日期、同一时段的重复观测只保留一份（`collapsed_rows` 记录被合并条数）。
- 相同键在不同批次出现不同数值时，该键标记为冲突（含逐对来源特征值与字段差异）。冲突未全部选择来源的版本不发布，任务也不能引用它。
- 每个来源选择绑定冲突指纹（`signature`）。批次变更导致冲突内容变化时，旧选择判为失效（`stale_resolutions`），不会被套用到新冲突，需重新选择。
- 每次修改生成新的 `CombinationVersion`，样本、来源批次、冲突与指纹固化在版本内。提交任务时复制该版本样本，排队期间修改组合不影响正在运行的研究。
- 分析按（站点、观测日期）分片配对，日末缺口不借用次日观测；版本号、样本指纹随结果、分发计划和归档 JSON 一并保留。

## 快速启动
```bash
cp .env.example .env
docker compose up -d --build --wait
docker compose exec -T backend python -m scripts.seed_demo
```
访问 http://localhost:18202；后端文档 http://localhost:19202/docs；数据库宿主端口 17702。
`SEED_DEMO=true` 自动幂等 seed；不覆盖用户修改。手动 seed 命令可重复执行。

## 演示账号与权限
|账号|密码|真实权限|
|---|---|---|
|admin@demo.local|Demo123!|接入、执行、批准、分发、暂停、读取与下载|
|analyst@demo.local|Demo123!|接入、组合、执行、读取与下载；不能批准或安排分发|
|viewer@demo.local|Demo123!|只读与下载|

## 技术与本地开发
Python 3.12 / FastAPI / SQLAlchemy / NumPy / SciPy / scikit-learn；PostgreSQL 16；Redis 7；Nginx；原生 HTML CSS JavaScript ES modules（用户指定）。后端所有校验、持久化和算法在服务端。无前端打包步骤。
后端：安装 backend/requirements.txt，设置 DATABASE_URL、REDIS_URL、JWT_SECRET、ARTIFACT_DIR 后在 backend/ 执行 `python -m migrations.initial`、`python -m scripts.seed_demo`、`uvicorn src.main:app`，另开 `python -m src.worker`。前端使用带 /api 反向代理的 Nginx，直接打开 index.html 不支持 API。

## 目录与工程约定
backend/src/{models,schemas,services,routes,controllers,middlewares,constants,config,utils}；backend/scripts/seed_demo.py；backend/migrations/initial.py。
frontend/src/{api,stores,types,components/common,hooks,pages,router,utils,constants}。
Role 枚举：admin/analyst/viewer；JobStatus：queued/running/completed/failed。后端 backend/src/constants/enums.py，前端 frontend/src/constants/enums.js；路由权限在 middlewares/auth.py；页面按相同角色控制操作入口。

## 环境变量与 Docker
COMPOSE_PROJECT_NAME=cycle-factors；FRONTEND_PORT=18202；BACKEND_PORT=19202；DB_PORT=17702；DB_PASSWORD、JWT_SECRET 见 .env.example；SEED_DEMO 默认 true。共享命名产物卷供后端下载与 worker 写入，数据库/Redis 各持久卷。
恰好五服务均有健康检查。Redis 队列加 SQL 排队状态兜底；worker 按 next_run 生成本地收件箱文件。周期 60 秒至 30 天。分发结果为批准分析的固定快照；若需新数据重新计算并建立新计划。当前不连接邮件或企业聊天。
错误响应、请求编号、Redis 每 IP 每分钟 240 次限流、JWT 和数据库操作审计。演示密钥与密码仅供本机模拟；生产部署前配置独立密钥与账号。

## 数据与验收
所有数据为固定随机种子生成的模拟业务数据，不能作为实际生产决策证据。项目独立算法、输入边界及业务局限详见 BUSINESS.md。测试与截图统一存放 ../../test-artifacts/gb-1003/，源码不含日志/截图/测试报告。
清理本项目演示数据：`docker compose down -v --remove-orphans`（会删除本项目命名卷）。

## License
MIT，见 LICENSE。
