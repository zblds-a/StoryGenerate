# 真实模型验收批次（Git `8b3beec`）

固定 Create 样本 12 例；第 01、02、03、04、05、07、10 例写出
`plan / delivery / evidence` 并标为 `READY`。第 06、08、09、12 例超时，
第 11 例 HTTP 503，错误见对应 `case_XX_error.json`。本批次结果为 **7/12**，
不满足发布通过门。

`case_XX_evidence.json` 记录 Git SHA、规则哈希、实际模型、Token 与延迟。
原始 Delivery 仅为自动化证据，尚未经过 10/12 人工四项评分。
尤其第 03 例估算 206 秒却目标 300 秒，并出现未批准的 `role-5`；
现有 `READY` 标志不能替代时长和角色人工复核。五分钟演示稿位于
`../5分钟演示广播剧脚本.md`，是以第 03 例为原案的编辑稿，并非
原 Delivery 的逐字复刻。
