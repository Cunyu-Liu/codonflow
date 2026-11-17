# 外部 baseline 统一协议（2026-11-17，development15后执行）

## 目标与顺序

主目标H0是检验CodonFlow能否在统一外部对照中超越现有方法，不是预设其已经超越。development15未完成前不计算或发布外部排名。先复核现有LinearDesign、GEMORNA、codonGPT输出，再决定哪些protein-only补实验必要；不得把不同阶段混成一张表。

## 已核实的原始输出与限制

- unique18 seeds0/1/2均有真实输出，独立MFE/NED复算一致，identity=100%。源文件为A6 schema：`methods[method].solutions`、`obj_vectors`、真实`n_unique`及成本字段。
- LinearDesign使用官方DP扫描，每基因仅少量真实解（示例5），`forward_calls=null`，生成器7次DP调用；不得随机补足至50/100/500。
- codonGPT通常100唯一解，长度超过1024 codons（含stop）为架构性排除，不能记0分或静默删除；autoregressive token forward与batched forward分开记录。
- GEMORNA请求100后真实唯一解约70–90，官方生成器无seed参数；去重/过滤过程必须披露，不能把请求数当唯一输出数。
- 旧`obj_vectors`第四轴是motif计数，A7为长度归一化motif penalty，不能直接把旧向量代入A7 HV。所有序列必须用A7冻结RSCU、GC、RNAfold和motif口径重新评分。
- A6 `elapsed_s`主要是生成时间，A7 learned/simple `elapsed_s`包含提议和终端评分。旧时间不得直接用于公平时间比；生成成本和终端scorer成本分开，任何公平时间比较必须重新端到端测量。
- 三个外部方法均是protein-to-CDS输入，不具备natural-source warm-start等价输入。禁止把它们的protein-only结果与CodonFlow natural-source结果写成同一因果比较。

## 分析线A：现有输出的实际预算复核

1. 对原始序列重新计算A7四目标、identity、NED、独立calibration下的参考域和原始Pareto front；记录真实唯一解与B=50/100/500可达性。
2. 只报告每个方法实际覆盖的预算和缺失预算；LinearDesign等不得随机填充，不能把缺失预算当0，也不能用低预算AUC冒充500预算AUC。
3. 输出原始Pareto、四目标best-at-actual-budget、真实唯一输出、NED、生成成本、架构排除和第三方预训练不可审计性。
4. 此线只是外部参考与边界，不形成CodonFlow胜负结论。

## 分析线B：protein-only公平补实验

1. 对所有方法使用同一蛋白输入和同一protein-only初始语义；与natural-source结果分表。CodonFlow的protein-only初始生成方式、随机种子和是否携带天然密码子信息必须显式记录，禁止偷用natural source。
2. 预先冻结每个方法请求预算、真实唯一scorer预算、B=50/100/500、缺失处理、成本口径和排除规则。请求500不保证500唯一解，缺失预算如实报告，不事后增加请求直到某方法获胜。
3. 如补生成，使用官方实现和冻结版本；请求预算在运行前固定，所有成功/失败/重复/非法输出保留。CUDA方法必须真实CUDA，禁止CPU静默降级。
4. 共同主要结局为独立calibration下anytime AUC与端到端wall-clock；辅助为Pareto、best-at-budget、NED、forward、terminal请求、唯一scorer和真实唯一输出。基因是统计单位，seed不是独立生物样本。
5. 所有外部结果仍先是开发证据；confirmation24是否启动另行评审，禁止根据外部结果事后选择基因或阈值。

## 验收与测试

- 18基因×3 seeds输入哈希、源蛋白和实际输出数完整；非有限目标、identity错误、未登记版本和错误RSCU直接失败。
- 测试旧motif不可误用、不同长度归一化、缺失预算不补零、架构排除、重复序列、无seed官方生成器和真实成本字段。
- 独立第二套实现重算AUC/NED/Pareto和成本，输出SHA256；不覆盖A6/A7历史结果。
- 在线B运行前另存真实dry-run、请求预算和并发。最终没有统一结果前，不宣称baseline已找全、SOTA或生物学有效性。
