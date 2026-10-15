# StoryGenerate 简短交接说明

交付内容：Create、Revise、Continue、Remix 故事生成后端，含大纲审批、异步任务、角色接入、历史版本及结构化导出。可开始团队联调；真实TTS、音频拼接、前端页面和硬件由其他团队负责。

**代码获取**：[GitHub仓库](https://github.com/zblds-a/StoryGenerate)，分支 `codex/storygenerate-handoff`；[PR #4](https://github.com/zblds-a/StoryGenerate/pull/4) 目标为 `codex/phase11-product-service`，未合并main。已验证完整交付快照为 [`0dec8480e3c1b01af66407ff063f825a3fd5dedb`](https://github.com/zblds-a/StoryGenerate/commit/0dec8480e3c1b01af66407ff063f825a3fd5dedb)，本说明为后续文档补充，不改变引擎。联调无需先合并；评审与签收后再合并研发集成分支。

## 代码位置（相对于仓库根目录）

|内容|具体位置|
|---|---|
|四操作统一工作流、请求/交付Schema|[4-引擎代码/drama_engine/workflow/](../../4-引擎代码/drama_engine/workflow/)，入口 `service.py`，合同 `schemas.py`|
|HTTP接口与服务启动|[4-引擎代码/drama_engine/service/](../../4-引擎代码/drama_engine/service/)，路由 `api.py`，命令入口 `__main__.py`|
|异步任务、Worker、角色库、下游适配|同上目录的 `runtime.py`、`worker.py`、`library.py`、`downstream.py`|
|数据库模型与迁移|[4-引擎代码/drama_engine/persistence/models.py](../../4-引擎代码/drama_engine/persistence/models.py)、[alembic/](../../alembic/)|
|角色Canon/Runtime模型|[4-引擎代码/drama_engine/characters/models.py](../../4-引擎代码/drama_engine/characters/models.py)|
|部署与工程测试|[Dockerfile.service](../../Dockerfile.service)、[docker-compose.yml](../../docker-compose.yml)、[tests/](../../tests/)|
|手动调用与交付自检脚本|[tools/handoff/](../../tools/handoff/)、[docs/handoff/examples/](examples/)|

## 说明文档位置

|阅读目的|具体文档|
|---|---|
|统一入口、交付范围|[docs/handoff/README.md](README.md)、[00-overview.md](00-overview.md)|
|架构、四操作与状态流转|[docs/handoff/01-architecture.md](01-architecture.md)|
|完整API、参数、请求响应|[docs/handoff/02-api-reference.md](02-api-reference.md)、[OpenAPI JSON](contracts/openapi.json)；运行后 `/docs`|
|照着操作的8套教程|[docs/handoff/03-manual-demos.md](03-manual-demos.md)|
|播放中改变剧情的方案与限制|[docs/handoff/04-direction-change.md](04-direction-change.md)|
|7份真实故事全文及原始JSON|[docs/handoff/05-story-gallery.md](05-story-gallery.md)、[samples/](samples/)|
|故事质量、Token、耗时与失败分析|[docs/handoff/06-quality-cost.md](06-quality-cost.md)|
|前端/业务后端与TTS对接|[docs/handoff/07-client-integration.md](07-client-integration.md)、[08-tts-integration.md](08-tts-integration.md)|
|Windows/Linux部署、配置与排障|[docs/handoff/09-deployment.md](09-deployment.md)|
|验收结果、证据与签收检查表|[docs/handoff/10-acceptance.md](10-acceptance.md)、[contracts/](contracts/)、[Phase11报告](../phase11/ACCEPTANCE.md)|

## 启动与调用

环境：Python3.11、PostgreSQL16；安装 `python -m pip install -e '.[service,test]'`。安全注入 `STORY_DATABASE_URL`、`STORY_API_KEYS`；Worker另需真实模型网关凭据与配置。具体命令、Docker和环境变量见部署文档，勿将密码/密钥写入仓库。

依次执行 `python -m drama_engine.service migrate`，分别启动 `python -m drama_engine.service serve` 与 `python -m drama_engine.service worker`。默认本机API为 `http://127.0.0.1:8000`，通过 `/health` 检查；这不是已部署的共享联调地址。

调用顺序：导入/选择角色 → POST `/v1/plans` → 轮询task → 查看/修改大纲 → 用户审批 → 轮询job → 获取故事版本 → 导出StoryDelivery/RenderManifest。**审批直接入队生成，可能产生模型费用。** 三种客户端示例见演示文档。

交接时双方还需确认：实际联调地址与网络权限、调用方principal/Bearer权限、模型费用承担与预算、业务/运维/TTS联系人。上述环境信息通过安全渠道另行提供，不在此虚构服务地址或联系人。

## 验收及接手要求

已有交付快照：685项工程测试、40项无模型真实HTTP检查通过；Phase11历史75次模型调用共1,317,167 Token，失败与重试有记录。原文样例未润色；本次仅补交接索引，不新增付费生成。

请接手同事先按README和教程独立完成一次全链路，并记录任务ID、问题及签收结果。独立真人走查、真实TTS/硬件仍未验收；无14岁以下年龄档或精确播放切片能力；样本集中于广播站题材，部分情节需局部内容修复，详见质量报告。
