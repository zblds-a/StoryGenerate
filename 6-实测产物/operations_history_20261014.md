# 保留批次索引

所有批次保留原始模型正文；工程测试替身与真实验收分开。自动READY与产物复核通过分别记录。

| 批次 | 实现提交 | 最终标签 passed / failed / blocked | 说明 |
| --- | --- | --- | --- |
| [operations_live_v1_20261014](operations_live_v1_20261014/manifest.json) | `8539a536` | 0 / 3 / 15 | 要求ID错误；Create拒绝。 |
| [operations_live_v2_20261014](operations_live_v2_20261014/manifest.json) | `eaf6808d` | 4 / 6 / 8 | 引文/范围合同缺陷；有中断恢复。 |
| [operations_live_v3_20261014](operations_live_v3_20261014/manifest.json) | `f513724b` | 5 / 3 / 10 | 大纲范围缺陷；有中断恢复。 |
| [operations_live_v4_20261014](operations_live_v4_20261014/manifest.json) | `3c0b1e85` | 15 / 2 / 1 | 日期/播出时刻正文问题，复核撤销通过；SSL未知用量；最终DB检查另发现并恢复遗留运行任务。 |
| [operations_live_v5_20261014](operations_live_v5_20261014/manifest.json) | `74f6171f` | 10 / 5 / 3 | 仅台词声称敲铃、无实际呈现；中间集结局误拒。 |
| [operations_live_v6_20261014](operations_live_v6_20261014/manifest.json) | `b9d5d5f3` | 14 / 2 / 2 | 时刻证据漏项；不变审批重试失败；另一个辅助路径断言未执行。 |
| [operations_live_v7_20261014](operations_live_v7_20261014/manifest.json) | `06a5a7bf` | 8 / 3 / 7 | “一点一点”数量表达误识别为时间，批次被修复替代。 |
| [operations_live_v8_20261014](operations_live_v8_20261014/manifest.json) | `45ac96ab` | 18 / 0 / 0 | 18项最终合格；共20次尝试2次不合格，Remix首轮最终新增同晚calendar约束，原两次产物保留。 |

上表是各批次当前主标签；早期attempts、自动通过撤销、未知消耗及成本见总报告acceptance.json。被中断的运行节点不可按零成本处理。

三次timeline_negative真实Judge反例保留；不能声称只换Strong就解决全部时间推理，第三次通过引文落地/显式时刻覆盖门阻止候选，未直接识别事件冲突的部分如实记录。

旧固定模板保存产物结构复核通过5/7，不能将旧6/7或旧616测试数当作当前四操作验收。