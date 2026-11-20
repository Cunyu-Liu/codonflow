# A8-RK：纯外部 RCS 对照任务记录

本文件只记录 pure external-RCS comparator 的冻结任务与验收状态；其他历史任务以主交接和 registry 为准。

## 2026-11-20：MAGE 纯外部 RCS 对照、论文 v32 与 PPT108 closeout

- [x] **拟合前冻结纯外部特征臂**：`pure_external_rcs` 仅含 variant RCS、相对 matched wild-type 的 RCS 差值及绝对差，不含 position、position interaction、codon/amino-acid identity、GC、local MFE 或其他 intrinsic 特征。复用 131 个 train+dev constructs 的冻结 OOF/folds，沿用 5 outer × 4 inner × 3 seeds × 6 alphas，新增 375 次真实拟合；33 个 test constructs 始终排除。协议 SHA256=`9efd39ef21672722adde333e28f4e1144983949dfab5a6437a1f45a68e930b45`，预注册提交=`0a08eb90c3ee787578f5fac1d5f01a2b2fe72a5d`。
- [x] **纯 RCS 替代失败**：主 seed 纯 RCS RMSE=`0.04929761172417739`、Spearman=`-0.13201530863899236`，intrinsic RMSE=`0.03413327461240379`、Spearman=`0.6123990835404937`。pure−intrinsic ΔSpearman=`-0.744414392179486`，95% CI=`[-0.9403491867053566,-0.5300791533185797]`，Holm p=`0.0002999850007499625`；ΔRMSE=`+0.015164337111773597`，CI=`[0.005846359530413134,0.02506527402042598]`，p=`0.009449527523623819`；两个 sensitivity seeds 方向均不利于纯 RCS，故 replacement=false。
- [x] **机制解释不变**：full−pure 与 intrinsic+RCS−pure 的两项终点均满足 development-only 支持规则，但这只是优于弱纯 RCS 臂，不等于优于 intrinsic。旧 full−intrinsic ΔSpearman/ΔRMSE 的 CI 均跨零、两项 Holm p=1；mechanism_increment=false、RK-G1=false，test 与生成训练仍未授权。
- [x] **科学独立验收**：正确环境 `/root/miniconda3/envs/llr_env/bin/python` 下 10/10 单元测试 PASS；独立实现重新抽取特征并重跑 375 fits、nested alpha、预测、bootstrap、permutation 和 Holm，174/174 PASS、max numeric delta=0；finalization 43/43 `PASS_PURE_EXTERNAL_COMPARATOR_CLOSEOUT`，推送后独立复验仍为 174/174。科学证据提交=`b95e1244537a23c95cdda986cb60e343cfd7e4da`，大型 predictions/logs/postpush 位于 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk03/mage_pure_external_nested_cv_v1/`。
- [x] **论文 v32**：新增 §6.28 `Pure external-RCS comparator on reused MAGE development folds`，真实稿件 SHA256=`6c3d2a0329a46ca70d4dd782748a06c60fbecbf91fd8d8fe5d7ea1c42e2b73f0`；独立与 postpush 均 100/100 PASS，可精确恢复 v31，摘要、旧章节和参考文献未改。提交=`d5959f73ac4f4812d614eee6d6c04d320dff38fc`；写作交付 shell 错误与 correction 保留，未修改科学正文门禁。
- [x] **在线 PPT108**：在 107/revision 69/`pZZ` 后仅追加第 108 页 `pZS`、revision 70；candidate 227/227、写后 553/553、closeout 32/32，真实在线截图视觉 PASS，旧 107 页及备注语义不变。两次 `+add-slide` server timeout 后均回读确认未落库；随后使用带幂等键的原生创建接口成功一次，未产生重复页。closeout 的报告字段和末尾换行修正不改变科学或在线内容。PPT 提交=`3460c2e07d6e44d09afa38e747db737aae939911`；归档位于 `/teams/HoulabData_1788502323/liucunyu/codonflow1031/rk03/mage_pure_external_nested_cv_v1/pure_external_ppt_v1/`。
- [ ] **仍未闭合**：本项只闭合旧 `rcs_only` 并非纯外部臂的歧义及纯 RCS 替代诊断，不闭合所有外部预训练模型替代、独立常数速度场、transport、functional untouched、full UTR–CDS remap、完整外部 SOTA 或真实功能验证；不得据此启动昂贵生成训练。
- [ ] **复现边界**：v32/pure-RCS/PPT108 后未运行完整项目 `pytest tests/`、干净环境安装或端到端总复现；上述 PASS 只覆盖冻结证据、定向测试、独立重算、论文与页面验收。权威工作树仍为 `/home/codonflow-a8-rk`、分支 `a8-rk`。
