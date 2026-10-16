# Revise 专项验收报告

实现提交：`45ac96ab1597a18f50a240c6069068cb79ca76fc`。

| 已实现 | 测试通过 | 真实模型通过 | 具备产品交付条件 |
| --- | --- | --- | --- |
| 是 | 是 | 是 | 是 |

最终批次通过 8/8 项；工程单元 658 项、PostgreSQL 6 项。

| 案例 | 结果 | Input / Output Token | 壁钟秒 | 产物 |
| --- | --- | ---: | ---: | --- |
| round_1_revise | passed | 86968 / 11945 | 107.844 | [证据](../operations_live_v8_20261014/round_1_revise/result.json) |
| round_2_revise | passed | 88789 / 10191 | 89.282 | [证据](../operations_live_v8_20261014/round_2_revise/result.json) |
| round_3_revise | passed | 91556 / 14233 | 118.016 | [证据](../operations_live_v8_20261014/round_3_revise/result.json) |
| special_arc | passed | 142797 / 50189 | 435.422 | [证据](../operations_live_v8_20261014/special_arc/result.json) |
| special_ending | passed | 75267 / 15563 | 147.812 | [证据](../operations_live_v8_20261014/special_ending/result.json) |
| special_episode | passed | 116657 / 27762 | 230.593 | [证据](../operations_live_v8_20261014/special_episode/result.json) |
| special_line | passed | 86709 / 13221 | 117.406 | [证据](../operations_live_v8_20261014/special_line/result.json) |
| special_whole_story | passed | 143577 / 51615 | 446.313 | [证据](../operations_live_v8_20261014/special_whole_story/result.json) |

## 原始产物复核

- round_1_revise：读取实际修改场景：林岚明确请周野一起核对控制台或设备状态，再决定下一步排查/修复方向；修改限于第一集指定场景，其余场景/集、ID与演绎标注逐字段一致；保留进水原因和角色身份，不提前兑现铃声
- round_2_revise：读取实际修改场景：林岚明确请周野一起核对控制台或设备状态，再决定下一步排查/修复方向；修改限于第一集指定场景，其余场景/集、ID与演绎标注逐字段一致；保留进水原因和角色身份，不提前兑现铃声
- round_3_revise：读取实际修改场景：林岚明确请周野一起核对控制台或设备状态，再决定下一步排查/修复方向；修改限于第一集指定场景，其余场景/集、ID与演绎标注逐字段一致；保留进水原因和角色身份，不提前兑现铃声
- special_arc：获批范围为完整两集；第一集以共同查外墙/递胶带由猜疑走向配合，第二集以稳夹电容和关心伤手延续信任；保留进水短路、修接头后主板故障及更换电容恢复底噪的结果；三声铃仍未兑现，角色职业与演绎者保持
- special_ending：只改第二集最后一场，以递验收单/笔、填写验收单的具体动作收束；保留合闸有底噪/主板恢复结果，未敲铃；其他场景与全部第一集逐字段相同；局部台词及变更行演绎可追溯
- special_episode：只重写第一集，用手电、挡风、递胶带推进合作，进水故障、修接头后主板故障和三声铃仍未兑现的结果保持；第二集完整保留，身份及演绎者不变，范围没有扩展
- special_line：只将ep1-s1-l1改为“咋又没声了？这都第几回了”口语表达，保持原意；其他台词/场景/集及标注逐字段一致
- special_whole_story：完整两集重写，以收起手机、递创可贴、稳住绝缘夹等具体动作推进信任；整体比源稿更紧凑；进水故障及原主要结果保留，林岚/周野身份稳定，结尾保留等待三声铃；没有手工改写正文，范围符合whole_story

## 逐项模型证据及定位

- round_1_revise / instruction：True；“先别动推子。周野，你帮我核对一下控制台的推子和指示灯状态，确认设备端无异常，我们再决定下一步排查方向。” (第1集/ep1-scene1/ep1-s1-l2)
- round_1_revise / timeline：True；“给我半小时换电容。修好后，我亲自敲墙上的三声铃，给街坊报平安。” (第1集/ep1-scene3/ep1-s3-l7)；“岚姐，电容买回来了！街角五金店最后两个。赶紧换上通电试试，街坊们都等着听降温预警呢！” (第2集/ep2-scene1/ep2-s1-l2)
- round_1_revise / edit_instruction：True；“先别动推子。周野，你帮我核对一下控制台的推子和指示灯状态，确认设备端无异常，我们再决定下一步排查方向。” (第1集/ep1-scene1/ep1-s1-l2)
- round_1_revise / preserve:facts：True；“防水胶圈老化，雨水倒灌。递我绝缘胶带。” (第1集/ep1-scene2/ep1-s2-l8)；“电容还没焊，现在推闸通电，主板瞬间就会击穿烧毁。把绝缘夹递给我。” (第2集/ep2-scene1/ep2-s1-l6)
- round_1_revise / preserve:identity：True；“怎么又断了？这都第几次了，街坊们还等着听天气预报呢！” (第1集/ep1-scene1/ep1-s1-l1)；“好嘞。哎，以前我总催你们维修班，还以为你们偷懒，原来这老设备这么难搞。对不住了啊。” (第1集/ep1-scene2/ep1-s2-l9)
- round_2_revise / instruction：True；“先别急着下定论。咱们先共同核对控制台设备状态，确认事实再决定下一步。把手电筒拿过来，照一下后盖。” (第1集/ep1-scene1/ep1-s1-l3)
- round_2_revise / timeline：True；“主控板差不多吹干了吧？等会儿修好试播，我敲三声老铜铃给街坊们报个平安，让他们安心，怎么样？” (第1集/ep1-scene3/ep1-s3-l2)；“全绿了！没异响！我拿老铜铃了啊，敲三声给街坊们报平安！” (第2集/ep2-scene3/ep2-s3-l4)
- round_2_revise / edit_instruction：True；“先别急着下定论。咱们先共同核对控制台设备状态，确认事实再决定下一步。把手电筒拿过来，照一下后盖。” (第1集/ep1-scene1/ep1-s1-l3)
- round_2_revise / preserve:facts：True；“看万用表读数，零线和地线阻值接近零，典型的短路。是漏水，不是剪线。拿上工具，顺着线去外墙看看。” (第1集/ep1-scene2/ep1-s2-l3)；“继电器卡死了。别碰铃铛，快切断总电源！” (第1集/ep1-scene3/ep1-s3-l8)；“输出电平不对，指针飘了。直接推上去会烧功放。” (第2集/ep2-scene3/ep2-s3-l8)
- round_2_revise / preserve:identity：True；“先别急着下定论。咱们先共同核对控制台设备状态，确认事实再决定下一步。把手电筒拿过来，照一下后盖。” (第1集/ep1-scene1/ep1-s1-l3)；“好嘞。林岚，其实你心里还是在乎这广播站的，只是嘴上不承认，对吧？” (第1集/ep1-scene2/ep1-s2-l7)
- round_3_revise / instruction：True；“先别下定论。拿上手电，跟我一起核对下设备状态，再决定下一步怎么修。” (第1集/ep1-scene1/ep1-s1-l4)；“看清楚了。接头全是水渍，屋顶漏水顺着墙皮渗下来的，没人剪线。” (第1集/ep1-scene2/ep1-s2-l2)；“拉动铃绳，却只有机械摩擦的咔咔声，铃铛没响。” (第2集/ep2-scene3/ep2-s3-l4)
- round_3_revise / timeline：True；“我今晚通宵修。” (第1集/ep1-scene3/ep1-s3-l11)；“这都天亮了，要不先睡会儿？万一傍晚没修好，大家也能理解。” (第2集/ep2-scene1/ep2-s1-l4)；“傍晚到了。岚哥，我坐好了，随时能开口。” (第2集/ep2-scene3/ep2-s3-l2)
- round_3_revise / edit_instruction：True；“先别下定论。拿上手电，跟我一起核对下设备状态，再决定下一步怎么修。” (第1集/ep1-scene1/ep1-s1-l4)；“看清楚了。接头全是水渍，屋顶漏水顺着墙皮渗下来的，没人剪线。” (第1集/ep1-scene2/ep1-s2-l2)；“拉动铃绳，却只有机械摩擦的咔咔声，铃铛没响。” (第2集/ep2-scene3/ep2-s3-l4)
- round_3_revise / preserve:facts：True；“看清楚了。接头全是水渍，屋顶漏水顺着墙皮渗下来的，没人剪线。” (第1集/ep1-scene2/ep1-s2-l2)；“防水盒……我想想。老站长抽屉里有个旧铁盒，以前装零件的，你看这个行不行？” (第1集/ep1-scene3/ep1-s3-l2)；“别动推子。击锤锈死了，我得拆开调一下。” (第2集/ep2-scene3/ep2-s3-l6)
- round_3_revise / preserve:identity：True；“哎哟我的祖宗！怎么又断了？这都第三回了，是不是外头那帮小混混嫌吵，故意把线给剪了？我这安抚街坊的稿子还没念完呢，急死个人。” (第1集/ep1-scene1/ep1-s1-l2)；“给。哎，我这拿话筒的手干粗活是不行，你看我这手抖得，差点照偏了。” (第1集/ep1-scene2/ep1-s2-l5)；“放边上。电容爆了，正在飞线。” (第2集/ep2-scene1/ep2-s1-l3)
- special_arc / instruction：True；“防水胶圈老化，雨水倒灌。递我绝缘胶带。” (第1集/ep1-scene2/ep1-s2-l4)；“给我半小时换电容。修好后，我亲自敲墙上的三声铃，给街坊报平安。” (第1集/ep1-scene3/ep1-s3-l7)；“说好了的。验收通过，由我来敲。” (第2集/ep2-scene3/ep2-s3-l7)
- special_arc / timeline：True；“给我半小时换电容。修好后，我亲自敲墙上的三声铃，给街坊报平安。” (第1集/ep1-scene3/ep1-s3-l7)；“岚姐，电容买回来了！街角五金店最后两个。赶紧换上通电试试，街坊们都等着听降温预警呢！” (第2集/ep2-scene1/ep2-s1-l3)
- special_arc / edit_instruction：True；“防水胶圈老化，雨水倒灌。递我绝缘胶带。” (第1集/ep1-scene2/ep1-s2-l4)；“给我半小时换电容。修好后，我亲自敲墙上的三声铃，给街坊报平安。” (第1集/ep1-scene3/ep1-s3-l7)；“说好了的。验收通过，由我来敲。” (第2集/ep2-scene3/ep2-s3-l7)
- special_arc / preserve:facts：True；“阻值归零，线皮没破，是内部击穿。没人剪线。” (第1集/ep1-scene1/ep1-s1-l6)；“防水胶圈老化，雨水倒灌。递我绝缘胶带。” (第1集/ep1-scene2/ep1-s2-l4)
- special_arc / preserve:identity：True；“怎么又断了？这都第几次了，街坊们还等着听天气预报呢！” (第1集/ep1-scene1/ep1-s1-l1)；“好嘞。哎，以前我总催你们维修班，还以为你们偷懒，原来这老设备这么难搞。对不住了啊。” (第1集/ep1-scene2/ep1-s2-l5)
- special_ending / instruction：True；“按流程，验收签字后，才能敲铃报平安。” (第2集/ep2-scene3/ep2-s3-l7)；“林岚按住麦克风开关，递给他一张维修验收单和一支笔。周野笑着接过笔，在验收单上郑重写下名字。笔尖划过纸面的沙沙声，在控制室里清晰作响。” (第2集/ep2-scene3/ep2-s3-l8)
- special_ending / timeline：True；“给我半小时换电容。修好后，我亲自敲墙上的三声铃，给街坊报平安。” (第1集/ep1-scene3/ep1-s3-l7)；“岚姐，电容买回来了！街角五金店最后两个。赶紧换上通电试试，街坊们都等着听降温预警呢！” (第2集/ep2-scene1/ep2-s1-l2)
- special_ending / edit_instruction：True；“按流程，验收签字后，才能敲铃报平安。” (第2集/ep2-scene3/ep2-s3-l7)；“林岚按住麦克风开关，递给他一张维修验收单和一支笔。周野笑着接过笔，在验收单上郑重写下名字。笔尖划过纸面的沙沙声，在控制室里清晰作响。” (第2集/ep2-scene3/ep2-s3-l8)
- special_ending / preserve:facts：True；“防水胶圈老化，雨水倒灌。递我绝缘胶带。” (第1集/ep1-scene2/ep1-s2-l8)；“周野跑去推上总闸。控制室电源灯亮起，喇叭传出轻微的电流底噪。” (第2集/ep2-scene3/ep2-s3-l2)
- special_ending / preserve:identity：True；“怎么又断了？这都第几次了，街坊们还等着听天气预报呢！” (第1集/ep1-scene1/ep1-s1-l1)；“好嘞。哎，以前我总催你们维修班，还以为你们偷懒，原来这老设备这么难搞。对不住了啊。” (第1集/ep1-scene2/ep1-s2-l9)
- special_episode / instruction：True；“风雨声里，周野默默侧身挡住漏风的窗缝，递上胶带。” (第1集/ep1-scene2/ep1-s2-l7)；“以前我总催你们维修班，还以为偷懒，对不住了啊。” (第1集/ep1-scene2/ep1-s2-l8)；“给我半小时换电容。修好后，我亲自敲墙上的三声铃，给街坊报平安。” (第1集/ep1-scene3/ep1-s3-l7)
- special_episode / timeline：True；“给我半小时换电容。修好后，我亲自敲墙上的三声铃，给街坊报平安。” (第1集/ep1-scene3/ep1-s3-l7)；“岚姐，电容买回来了！街角五金店最后两个。赶紧换上通电试试，街坊们都等着听降温预警呢！” (第2集/ep2-scene1/ep2-s1-l2)
- special_episode / edit_instruction：True；“风雨声里，周野默默侧身挡住漏风的窗缝，递上胶带。” (第1集/ep1-scene2/ep1-s2-l7)；“以前我总催你们维修班，还以为偷懒，对不住了啊。” (第1集/ep1-scene2/ep1-s2-l8)；“给我半小时换电容。修好后，我亲自敲墙上的三声铃，给街坊报平安。” (第1集/ep1-scene3/ep1-s3-l7)
- special_episode / preserve:facts：True；“防水胶圈老化，雨水倒灌。递我绝缘胶带。” (第1集/ep1-scene2/ep1-s2-l6)；“主控板因进水短路冲击烧毁了。” (第1集/ep1-scene3/ep1-s3-l5)
- special_episode / preserve:identity：True；“怎么又断了？这都第几次了，街坊们还等着听降温预警呢！” (第1集/ep1-scene1/ep1-s1-l1)；“以前我总催你们维修班，还以为偷懒，对不住了啊。” (第1集/ep1-scene2/ep1-s2-l8)
- special_line / instruction：True；“咋又没声了？这都第几回了，街坊们还等着听天气预报呢！” (第1集/ep1-scene1/ep1-s1-l1)
- special_line / timeline：True；“给我半小时换电容。修好后，我亲自敲墙上的三声铃，给街坊报平安。” (第1集/ep1-scene3/ep1-s3-l7)；“岚姐，电容买回来了！街角五金店最后两个。赶紧换上通电试试，街坊们都等着听降温预警呢！” (第2集/ep2-scene1/ep2-s1-l2)
- special_line / edit_instruction：True；“咋又没声了？这都第几回了，街坊们还等着听天气预报呢！” (第1集/ep1-scene1/ep1-s1-l1)
- special_line / preserve:facts：True；“防水胶圈老化，雨水倒灌。递我绝缘胶带。” (第1集/ep1-scene2/ep1-s2-l8)；“电容还没焊，现在推闸通电，主板瞬间就会击穿烧毁。把绝缘夹递给我。” (第2集/ep2-scene1/ep2-s1-l6)
- special_line / preserve:identity：True；“咋又没声了？这都第几回了，街坊们还等着听天气预报呢！” (第1集/ep1-scene1/ep1-s1-l1)；“别动推子。不是信号中断，是电源短路。” (第1集/ep1-scene1/ep1-s1-l2)
- special_whole_story / instruction：True；“防水胶圈老化，雨水倒灌。递我绝缘胶带。” (第1集/ep1-scene2/ep1-s2-l5)；“给我半小时换电容。修好后，我亲自敲墙上的三声铃，给街坊报平安。” (第1集/ep1-scene3/ep1-s3-l7)；“周野撕开创可贴推到手边，双手紧握绝缘夹，稳稳夹住电容。” (第2集/ep2-scene2/ep2-s2-l4)；“说好了的。验收通过，由我来敲。” (第2集/ep2-scene3/ep2-s3-l7)
- special_whole_story / timeline：True；“给我半小时换电容。修好后，我亲自敲墙上的三声铃，给街坊报平安。” (第1集/ep1-scene3/ep1-s3-l7)；“岚姐，电容买回来了！赶紧换上通电，街坊们等着听降温预警呢！” (第2集/ep2-scene1/ep2-s1-l3)
- special_whole_story / edit_instruction：True；“周野默默收起手机，剥好胶带递上。林岚满手泥水，接过胶带缠绕。” (第1集/ep1-scene2/ep1-s2-l6)；“给我半小时换电容。修好后，我亲自敲墙上的三声铃，给街坊报平安。” (第1集/ep1-scene3/ep1-s3-l7)；“周野撕开创可贴推到手边，双手紧握绝缘夹，稳稳夹住电容。” (第2集/ep2-scene2/ep2-s2-l4)；“林岚指了指墙上的黄铜铃铛。周野愣了一下，笑着放下麦克风，伸手向铃铛。” (第2集/ep2-scene3/ep2-s3-l8)
- special_whole_story / preserve:facts：True；“防水胶圈老化，雨水倒灌。递我绝缘胶带。” (第1集/ep1-scene2/ep1-s2-l5)；“电容没焊，现在推闸主板瞬间击穿。把绝缘夹递我。” (第2集/ep2-scene1/ep2-s1-l7)
- special_whole_story / preserve:identity：True；“怎么又断了？街坊们还等着听天气预报呢！” (第1集/ep1-scene1/ep1-s1-l1)；“好嘞。以前我总催你们维修班，还以为你们偷懒，原来这么难搞。对不住了。” (第1集/ep1-scene2/ep1-s2-l7)

单元与数据库测试使用显式测试替身，真实模型状态仅由本批次真实 Provider 产物判定。三轮样本不代表规模化稳定性。
