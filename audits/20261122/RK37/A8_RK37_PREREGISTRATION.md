# A8-RK37 预注册卡 · 跨研究翻译占据序列模型转向

## 触发与科学问题

RK36 的 label-free 可行性审计未发现满足 R1–R7 的独立精确起始窗运输数据，正式触发分支 2：停止把 start-aware MFE 当作既定核心创新，转向有数据支持的功能序列模型/翻译动力学。RK37 不再切分 Kudla/Mordstein 结构窗口，也不读取 functional untouched。

RK05 在 Mohammad16→Subtelny14 跨研究任务上留下两个明确失败：RiboMIMO 的 TB-MSE 输给 source-mean constant，转录本内 Pearson 输给 position ridge；constant 的 TB-MSE 又低于两个学习模型。RK37 检验一个固定的局部密码子、转录本内中心化、source-mean 锚定 ridge 能否同时超过这两个最强旧对照。Subtelny14 已被 RK05 观察并用于形成本问题，因此本实验是冻结的回顾性后续诊断，不是 untouched 或独立确认。

## 冻结数据与隔离

- 原始矩阵、SHA、official eligibility/normalization/mask 与 RK05 完全一致：Mohammad16 1,179 eligible；Subtelny14 3,921 eligible；exact CDS overlap=0。
- 三个种子 1234/2345/3456 复现 RK05 source-only split：1,062 train、117 validation。
- target coverage 仅用于复现已冻结的 eligible 集合。所有 source 拟合、alpha 和部署选择完成前，不读取 target 归一化结局、旧 target 预测或任何 target 指标。
- 所有 alpha 仅由 source-validation TB-MSE 选择；主候选固定为 `local_centered_anchored`，不能根据 target 改选其他臂或种子。

## 模型与判别分解

唯一拟合为 3 seeds×4 families×4 alphas=48 次 Ridge。四种 family 为 position/local × raw/transcript-centered；alpha=[0.1,1,10,100]，与 RK05 相同。position 是旧 86 维特征；local 是七密码子窗口加位置/长度特征的 477 维稀疏表示。

均值锚定在每个转录本的 masked prediction 上执行：`p_anchor=p-mean(p)+source_train_global_mean`。它不读取 target outcome，且保持转录本内 Pearson/Spearman 不变。辅助臂区分局部上下文、centered target 和锚定校准；既有 RiboMIMO 预测只作 raw/anchored 次要诊断，不重训。

## 两个确认性终点

主种子 1234，20,000 次整转录本 paired bootstrap 与 sign-flip permutation，两个终点统一 Holm：

1. `constant_mse - local_centered_anchored_mse`：必须 >0，95% CI 下界 >0，Holm p<0.05。
2. `local_centered_anchored_pearson - position_raw_unanchored_pearson`：必须 >0，95% CI 下界 >0，Holm p<0.05；仅在两者均有限的转录本上配对并报告排除数。

两个效应在 2345/3456 也都必须同号为正。只有全部满足才记 `DUAL_DIAGNOSTIC_PASS`。该标签仍不等于 SOTA；任一失败都使跨研究翻译任务保持未解决，并按失败组件继续诊断。

## 复现与不可声称事项

生产后由不导入生产模块的独立程序从原始矩阵重建全部特征、48 次拟合、预测和统计，再做固定科学 commit 的 clean checkout reproduction。所有大数组、预测和日志在 teams；代码和轻量报告在 /home。

本实验只涉及 normalized ribosome occupancy proxy，不是直接物理速度；是 exact-CDS-disjoint study OOD，不是 homology/protein OOD；不是功能 untouched、前瞻 DBTL、wet-lab、RK-G1、生成训练授权或完整外部 SOTA。CPU wall time 仅记录，不构成统一 time-matched 成本优势。
