# Journal 2026-11-12 · A7 执行恢复与合同同步

## 1. 本轮范围

- 逐份读取本地 `交接文档/` 全部 16 份材料；以 A7 warm-start synonymous CDS editing 合同为准，旧 scaling/RLOO/SOTA 与 arbitrary-corruption 模型结果均不进入新科学结论。
- 建立执行计划 `codonflow-main/docs/plans/2026-11-12-a7-g0-recovery.md`。
- 本轮未启动训练、未运行 GPU 评测、未修改 PPT，未将任何 smoke/proxy 结果写成结论。

## 2. 已确认的合同状态

- 当前仍为 P1/G0，G1–G4 不得越过前置门。
- 交接证据记录 confirmation24、D5 train RSCU 和 24/24 calibration pool 已完成并验证；执行时仍须在实际实例复核路径、record、hash、source role 和 scale。
- unique18 seed-0 有 18/18、五方法完成记录；seeds 1/2 与全量 MFE/NED 独立重算未完成。
- 全量数据来源、release、清洗数量守恒、分布和元数据审计未闭环。
- 没有有效的新 synonymous checkpoint；不得从旧 v4 权重恢复或评测。

## 3. 文档与配置修复

- 更新 `交接文档/spec.md` 与 `codonflow-main/docs/handover/spec.md`：写入 `/home` 代码、`/teams` 大型资产、CUDA 强制和并行不得越门的执行约束。
- 更新两处 tasks/checklist：消除确认集、RSCU、calibration 和 seed-0 状态漂移，新增 T1.8 GPU/环境验收。
- 更新 `configs/a7_data_protocol.json`：记录 confirmation24/RSCU/calibration 路径和完整 SHA256，同时明确状态为 handoff-verified、remote-recheck-required。
- 更新 `RECOVERY_A7.md` 和 `RUNBOOK_NEXT.md` 的当前执行状态。

## 4. 远端连接事件与证据边界

- px1 `px1-jcy.matpool.com:27882`：SSH 返回 `Connection closed by 125.71.97.44 port 27882`。
- px2 `px2-jcy.matpool.com:29375`：初次 askpass 文件无执行权限，修正权限后连接仍被远端关闭；随后通过 `sshpass -e` 使用本机 askpass 提供凭据，仍返回 `Connection closed by 125.71.97.44 port 29375`。
- 两端口 TCP 可达，但这不等于 SSH 会话、GPU 或数据可用。未获得本轮 `nvidia-smi`、CUDA matmul、进程或资产输出。
- 处置：保留失败证据，不启动 CPU 替代训练；后续先诊断 SSH 服务端/实例状态，再执行 G0 在线核验。

## 5. 验证记录

- `configs/a7_data_protocol.json` 已通过 `python3 -m json.tool` 解析及路径、哈希、记录数、CPU fallback 禁止断言。
- 两处 spec/tasks/checklist 已做逐字节一致性与 SHA256 检查；三份镜像均一致。
- 本地完整回归为 **128 passed, 1 skipped**，不是交接记录的 131 passed。GitHub `origin/main=4f3dac9` 尚未包含本地 A7 文件；远端共享副本可能另有 3 项测试，必须在 SSH 恢复后核对，不得把本地计数写成远端计数。
- 本地目录原为无 `.git` 的源码归档，现已关联 GitHub 并提交 `3b45775 feat: add A7 protocol and synchronize recovery contract`，提交前 `git diff --cached --check` 通过。
- 首次标准 push 遇到 HTTP/2 framing error；改用 HTTP/1.1 后遇到 GitHub 443 连接超时。代码尚未确认上传，不强推、不改写历史。

## 6. 下一步

1. 完成合同副本三重核对并运行本地完整回归。
2. 恢复 SSH 后先保存代码版本、GPU/驱动、CUDA matmul 和完整测试证据。
3. 在线复核既有资产，不重复生成 calibration；并行完成全量数据审计与 unique18 seeds 1/2、MFE/NED 独立重算。
4. 只有 C2 全部通过才启动从零 `M_SYN_D4_*` 训练；训练持续到注册的独立 val plateau，保存完整日志、训练状态和哈希。

## 7. unique18 独立 MFE/NED 复算工具

- 新增 `scripts/a7_recompute_unique18.py` 与 `tests/test_a7_recompute_unique18.py`。工具不修改原 JSON，只从冻结 solutions 重算 MFE/NED 和 CAI/GC/motif，并另写审计结果。
- 强制核对 source/benchmark/RSCU 哈希、record/seed、identity、真实唯一解数、目标向量形状和有限性；缺失方法/seed、重复或错位序列均不能通过。
- 首轮目录契约测试因本机缺少 ViennaRNA 失败，保留该事实；测试改为显式注入固定 fold 值验证逻辑，真实运行不在缺少 ViennaRNA 时降级或伪造数值。
- 最终 focused tests：**19 passed**；完整回归：**132 passed, 1 skipped**。这证明复算工具契约，不证明真实 unique18 已完成复算。
- GitHub 标准 push 再次因 443 连接超时失败；px2 本次为 `Permission denied`，未获得 SSH 会话。

## 8. GitHub 同步确认

- 本地提交 `3b45775`、`4796efe`、`f57d10c` 已通过标准 `git -c http.version=HTTP/1.1 push -u origin main` 上传。
- GitHub `main` 已推进至 `f57d10c`；未强推、未改写历史。

## 9. px1 在线核验与 synonymous 修复合并

- 用户提供新 px1 凭据后 SSH 恢复。远端共享副本完整回归确认为 **131 passed, 1 skipped**。
- px1 `torch 2.14.1+cu132` 可导入，但 `torch.cuda.is_available()=False`、`device_count=0`；`nvidia-smi` 输出为空，CUDA assert 退出码 1。证据保存于 `07_a7_data/gpu_px1_20261112_{nvidia-smi,cuda-check}.txt`，未启动任何训练。
- 通过 Git bundle 找回共享提交 `1bdc4061`，合并至 GitHub 主线为 `3022f11`；只保留代码、3 项 synonymous 契约测试，历史 journal 冲突采用当前 A7 版本。合并后本地完整回归 **135 passed, 1 skipped**，已标准 push。
- 新增 `a7_verify_frozen_assets.py` 与 3 项契约测试。px1 实际验收 confirmation24/RSCU/calibration24 全部通过；报告 `07_a7_data/frozen_asset_verification_20261112.json`，SHA256=`fe45f06697f08eb47dbbddd5bee84062dbe4bd0ca9be8b33fa53606ca7f15879`。
- 六个 D4/D5 train/val/test 全量 CPU 数据审计已并行启动；完成前不得勾选全量分布审计或 G0。

## 10. 全量审计发现非 ATG 部分 CDS 并修正分层口径

- 六个 split 的记录数与合同一致，但 v1 审计把 `start != ATG` 计入 `n_valid_cds` 失败；进一步分解确认所有此类记录仅为非 ATG，没有 alphabet/frame/stop/length 错误。
- 历史 `clean_cds` 与 A7 主操作合法性均不强制 ATG。非 ATG 记录可能为部分 CDS，必须作为质量与选择偏差披露，不能暗中删除，也不能错误称为操作非法。
- `a7_data_audit.py` 新增 `n_operator_legal`、`n_atg_start` 和口径定义；`n_valid_cds` 保留完整 ATG+长度质量层，CAI/蛋白统计覆盖全部操作合法序列。新增非 ATG 契约测试。
- v1 结果保留作审计轨迹，v2 六个 split 复算已启动。原始逐物种 FASTA 与下载日志未找到；已恢复 `download_v3_wave2.sh`，Ensembl release-112 URL 证据可追踪，但不能声称原始下载与逐步过滤记录已完整。

## 11. 六个 split 全量分布验收与代码部署

- v2 六个 split 均满足：记录数符合合同、`n_operator_legal=n`、唯一蛋白数符合合同、D5 未映射簇为 0。非 ATG 数分别为 D4 train/val/test=57,771/7,289/7,397，D5=57,803/7,439/7,209；作为可能部分 CDS 的质量限制保留。
- 汇总 manifest：`07_a7_data/full_audits_20261112_v2/manifest.json`，SHA256=`5950f13e65504d7b530b74ba0b276d333763a6b16e7ff8a1436938d5bdf821ad`，`passed=true`。
- GitHub `main=5f0f01b` 已通过 bundle 部署为 `/home/codonflow-a7`，旧 `/home/codonflow` 未覆盖；远端新工作副本完整回归 **139 passed, 1 skipped**。
- `v3_all` 862,240 条审计与 unique18 seed-0 MFE/NED 复算仍未完成；进程在远端运行，未重复启动。

## 12. v3_all 全量源数据审计通过

- `v3_all.fasta` 实际审计通过：862,240 条 ID 均唯一，全部操作合法，SHA256=`5e106f9e…`；797,386 个唯一 CDS、776,569 个唯一蛋白。
- 非 ATG 记录 73,445 条，保留为可能部分 CDS 的质量限制。长度 300–6000 nt、均值 1602.57 nt，GC 均值 0.51431，CAI 均值 0.78948。
- 审计文件 `full_audits_20261112_v2/v3_all.json`，SHA256=`01ceeb16dc55e5b8086aa363dfeccdf21cae8a89fb60db293a2b04e091f30047`。
- 汇总 manifest 已加入 v3_all，更新后 SHA256=`ba39f7641eba74ddaaf51d62be10ede1744f120213c16da3dbc7f8fdbda3edd3`。
- unique18 seed-0 仍在远端复算；复算器已新增 record-id 分片，完整回归 **139 passed, 1 skipped**，提交 `900027c` 待 push。

## 13. NED 性能瓶颈与依赖修复

- seed-0 长任务的主进程持续消耗 CPU、fold workers 空闲，定位到远端缺少 `rapidfuzz`，NED 使用纯 Python 两两 Levenshtein。
- 在 `codonflow` 环境安装 `rapidfuzz=3.14.5`，并用实际函数与纯 Python 距离逐项验证一致。未停止当前任务；`pairwise_ned` 会在后续调用动态使用加速实现，距离定义不变。
- `environment.yml` 与 `pyproject.toml` 的 eval 依赖已补 `rapidfuzz`。首次验证命令因未设置 `PYTHONPATH` 失败，随后在 `/home/codonflow-a7` 以 `PYTHONPATH=src` 验证通过。
- seed-0 尚未产出最终 JSON，仍不得标记复算完成。

## 14. 25 物种元数据恢复

- 从冻结 transcript ID 命名规则恢复 22 类 Ensembl 前缀、FlyBase、WormBase 和酵母映射；未识别 Ensembl 前缀直接失败，不猜测 family。
- `v3_all` 与六个 split 均精确识别 25 个物种，共 2,415,155 条输入记录全部映射成功。
- 产物：`full_audits_20261112_v2/species_distribution.json`，SHA256=`541b8de1f9c01c91a92ee2aeaf22133faf4b43e0caf48076aee411190fb26563`；`07_a7_data/species_map.json`，SHA256=`479d0c745f50605a6a7171884d68895ba68e522abe3cd55c659987370919efef`。
- 新增 `a7_species_audit.py` 与 3 项契约测试。该映射只支持物种占比描述，不支持 species OOD。

## 15. px2 GPU 硬件验证与环境恢复

- 用户提供 px2 凭据后，实测 RTX 5090 32GB、driver 595.84/CUDA 13.2，其他项目两个 `llr_env` 进程约占 9GB，未触碰。真实同步 CUDA matmul 成功：`torch.Size([512, 512]) cuda:0`。
- 该硬件验证使用现有 `llr_env` 的 torch 2.11.0+cu128，仅证明 GPU 可用；不得据此复用其他项目环境训练。
- 最新代码已通过 bundle 部署至 `/home/codonflow`，提交 `fc5eba4`。独立 `codonflow` 环境重建首先遇到阿里云 Conda 镜像 404，随后 channel-alias 参数/环境变量未生效；改用隔离 `/home/codonflow-condarc`，不修改全局配置。
- px1 再次验证仍 `CUDA=False N=0`，无 CPU 替代训练。

## 16. unique18 seed-0 独立复算通过

- 实际完成 18/18：MFE、NED、CAI/MFE/GC/motif 四轴、identity、真实唯一解数、source/benchmark/RSCU 哈希和 record/seed 全部匹配；`complete_all_requested_seeds=true` 仅针对请求的 seed 0。
- 报告：`07_a7_data/unique18_seed0_independent_mfe_ned.json`，SHA256=`c0425d18b58e523b55a9275b74c96283f907e73babb9d06a13865bfe15b1af9f`，RNAfold 2.7.2。
- seeds 1/2 尚未生成与复算，不将 seed-0 写成全部 seeds 完成。
- 新增 25 物种 release-112 恢复管线与契约测试；完整回归 **146 passed, 1 skipped**。

## 17. px2 独立环境验收与并行任务启动

- Conda 镜像404、Python3.9 错误 venv、低速重复下载和 `/teams` 不支持 symlink 均保留失败记录；最终通过 tar 归档部署 `/root/miniconda3/envs/{codonflow,pc_cng}`，未复用 `llr_env`。
- px2 CodonFlow 环境完整回归 **142 passed, 1 skipped**；torch 2.14.1+cu132、ViennaRNA 2.7.2、rapidfuzz 3.14.5、torchtext 0.6.0 和真实 CUDA matmul 全部通过。
- LinearDesign 在正确 cwd 用真实短蛋白运行成功；codonGPT/GEMORNA 权重路径已核验。
- px2 无 tmux，改用 nohup。unique18 seeds 1/2 已并行启动（PID 5171/5172），codonGPT 权重加载成功，日志与 PID 保存在 `07_a7_data/unique18_seed{1,2}_{run.log,pid}`。
- 25 物种 release-112 恢复已启动（PID 19887），输出 `07_a7_data/raw_release112/`，不覆盖历史 cleaned 数据。

## 18. PPT 第 45 页状态记录

- 在 `CodonFlow-中期汇报-20261009.pptx` 末尾新增 A7 G0 状态页：862,240 条/25 物种、24/24 校准、seed-0 18/18、px2 CUDA 与 142 项测试基线。
- 页面明确 seeds 1/2 与 raw recovery 仍在进行，G0 未关闭、主训练未启动，不含模型性能或可提交预印本结论。
- 验证：PPT 重开为 45 页、关键文本存在、25 个形状无越界；LibreOffice PDF 第 45 页渲染为 1601×900，非空白比例正常。临时验证文件已清理。

## 19. GEMORNA Triton 编译失败与断点恢复

- seeds 1/2 首次运行在 GEMORNA 阶段停止：`RuntimeError: Failed to find C compiler`。LinearDesign 已完成文件保留，部分结果不视为完整 seed。
- 使用 `CC=/root/miniconda3/envs/pc_cng/bin/x86_64-conda-linux-gnu-cc` 进行 `MAA` 单次真实 GPU 验证，成功生成 `ATGGCCGCC`，随后以相同 CC 和 `--resume` 重启两条任务，日志追加不覆盖。
- 失败触发的复算 JSON 为 `n_matching=0/18`、`complete=false`，已重命名为 `unique18_seed{1,2}_independent_mfe_ned_partial_before_cc_fix.json`；新 watcher 等待新 PID，不沿用部分审计。
- release-112 原始恢复正在写入 gzip 临时文件，尚无完成物种，未提前勾选 provenance。

## 20. codonGPT 批量自回归优化

- 顺序实现每个样本逐密码子 forward，seed 任务长时间无完成项。先停止自己的 watcher 和可恢复任务，保留 LinearDesign 断点，再改为同长度样本批量自回归；forward/scorer 成本定义不变。
- 假模型契约测试验证批量 forward 和蛋白身份；修正测试中 M+A+stop 应为 3 次调用的错误预期。完整回归 **147 passed, 1 skipped**。
- 真实 GPU smoke：C31E10.3b.1、100/100 唯一解、identity=1.0、17,800 forward、2.7959 秒。产物仅作性能/接口验证，不作科学结果。
- 已用批量实现和正确 CC 恢复 seeds 1/2，并重挂复算 watcher。

## 21. 批量 forward 成本口径纠正

- 批量 smoke 的 17,800 是样本×token 等效计算量，不是实际模型调用；实际批量 forward 为 178。为避免成本误报，`forward_calls` 改为真实批量调用数，新增 `autoregressive_token_forward_evaluations` 保存等效量。
- 新契约测试同时检查两种计数，focused tests 通过。旧部分文件移入 `07_a7_data/quarantine_pre_forward_cost_fix/`，未手改 JSON。
- 已停止自己的 watcher/父进程/GEMORNA 子进程，并以正确成本口径重新生成 seeds 1/2；批量 smoke 仅作接口验证，不进入科学结果。

## 22. GEMORNA 持久化生成

- 官方 `src/generate.py` 每次调用都会重建模型并加载权重。新增 `gemorna_persistent.py`，在同一进程顺序调用官方 `model.gen`，不改采样算法、不增加 seed 参数。
- 成本分开记录：`generator_calls=1` 为一次持久化子进程，`official_model_calls=n` 为官方生成调用数，`forward_calls=null` 仍为官方不可见。
- 真实 GPU smoke：10/10 唯一解、identity=1.0，持久化生成耗时 29.87 秒；focused tests 通过。
- 已停止自己的旧 GEMORNA 子进程并以 `--resume` 切换 seeds 1/2，已完成 LinearDesign/codonGPT 不重跑。

## 23. 新口径首批产物与首个恢复物种

- seeds 1/2 首个 codonGPT 均为 100/100 唯一合法解；`forward_calls=178`、`autoregressive_token_forward_evaluations=17,800`，生成约 3.74/3.78 秒。GEMORNA 已进入持久化模式。
- 首个完成恢复物种 `takifugu_rubripes`：输入 52,243、保留 50,176，与 v3_all 物种计数一致；原始/清洗哈希已写入 recovery.json。
- 完整回归 **149 passed, 1 skipped**；GEMORNA 持久化提交 `d8f6306` 待 push。

## 24. Watcher 与人类来源版本修正

- 旧 watcher 的子进程在 baseline 完成前再次生成 `0/18 matching`，已隔离为 `partial_early_watch` 并停止自动链。后续只在 18/18 完成后手动复算；当前两条 baseline 已完成 2/18。
- 人类 release-112 与 v3_all 只有 71,506 个共享 base ID，且版本号系统变化；其余已恢复物种计数一致。历史人类来源为 BioMart 当前版本，经 URL 验证 release-116 存在、release-117 不存在。
- 注册表改为仅人类 release-116，其余物种保持 release-112；`source_url` 支持 per-record release 并新增测试。人类116独立恢复已启动，不把112版本差异写成原数据丢失。
- seeds 1/2 的首个 codonGPT 成本已复核：真实 forward=178，等效 token forward=17,800。

## 25. unique18 按基因分片并行

- 顺序任务已完成 3/18 后，新增 `a7_run_unique18_shards.py`：只跳过 `status=done` 的基因，running/partial 保留并重跑。
- 每个 seed 3 个并发基因，总计 6 个独立任务；MFE_PROCS=2/任务，保留正确 CC 与持久化 GEMORNA。已完成的 3 个基因不重跑。
- 不再设置自动复算 watcher；分片全部结束后手动进行三 seed 验收。
- release-112 非人类已恢复 4 个物种；人类116下载仍在进行。

## 26. G0 自动裁决器与 CUDA 证据

- 新增 `a7_g0_gate.py`：只有全量分布、冻结资产、25 物种正确 release、三 seed 独立复算和 CUDA matmul 全部通过才输出 `passed=true`。
- source manifest 逐物种核对 cleaning 数量守恒、哈希和实际文件；人类只接受 release-116，其余物种 release-112。缺失 seed 或物种均有独立检查项。
- 新增通过/缺失两类契约测试；px2 真实 CUDA 证据保存为 `07_a7_data/cuda_evidence_px2.json`，包含同步 matmul、设备、形状和版本。
- 当前 G0 仍未裁决通过，待原始恢复和 seeds 1/2 完成后运行统一入口。

## 27. 分片进展与 G0 命令固化

- 当前 seed1 完成 6/18、seed2 完成 8/18；分片文件与 done 状态分别核对，未运行自动复算。
- release-112 已恢复 6 个非人类物种，人类116仍未完成；G0 保持未通过。
- `RUNBOOK_NEXT.md` 已写入统一 `a7_g0_gate.py` 命令，只有 `g0_gate.json passed=true` 才允许启动训练。
- G0 功能提交 `2a1c64f` 的 GitHub push 仍间歇失败，后续继续标准推送，不强推。

## 28. 分片 OOM 与并发调整

- seed2 的 `ENSACAT00000037188.1` 在 GEMORNA 初始化时报 `CUDA out of memory`，driver 保留完整 traceback；不是数据错误，已完成文件不受影响。
- 总并发 6 对其他项目动态余量不足。只停止自己的 driver/子进程，将每个 seed 降为 2 个并发（总计 4），按 done 状态断点续跑；若仍 OOM 继续降并发，不使用 CPU 替代。
- release-112 已恢复 9 个非人类物种，人类116仍在下载。

## 29. seed2 进一步限流

- seed2 的同一基因再次失败，按预设降级规则将 workers 从 2 降为 1；seed1 保持 workers=2。只停止自己的 driver/子进程，done 文件不重复生成。
- 当前 GPU 仍有其他项目高负载，不使用 CPU 替代。原始恢复保持 9/25，人类116下载中。

## 30. G1 非退化验收入口

- 新增 `a7_g1_behavior.py`：冻结 checkpoint SHA256、强制 CUDA、每基因至少 100 paired 样本，检查 identity/legal、非源率、唯一解和最大单序列频率。
- 记录 stay-p、实际路径 P(edit)、实际采样位置覆盖、两种奖励 profile 响应和 uniform 逐串重合；不使用枚举全部位置冒充覆盖。
- 契约测试覆盖多样输出与复制塌缩；修正 overlap 是集合大小而非样本数的测试预期。完整回归 **154 passed, 1 skipped**。

## 31. 人类 release 选择纠偏

- release-116 实际恢复 298,824 条，新增 227,289 个 base ID；release-112 仅新增 7,113 个。两者对旧人类 base ID 覆盖率均约 99.5%，但 release-112 明显更接近历史来源。
- 先前仅根据旧 BioMart 时间推测 release-116 不充分，现撤回该选择。注册表恢复为人类 release-112，release-116 产物保留隔离，不用于训练或 G0。
- A7 正文同步纠正为人类 release-112，并披露 release-116 被评估后排除。当前原始恢复12/25，seeds均11/18。

## 32. G1 真实 CUDA smoke

- `a7_g1_behavior.py` 支持按 record-id 选择三个开发基因；随机初始化 checkpoint 仅用于接口验证，SHA256=`285593ef…`。
- 三个基因×100 paired 样本的完整 CUDA 流程成功，`g1_random_smoke.json passed=true`；这不是训练模型，不能作为 G1 科学通过或性能结果。
- 首次 checkpoint 创建命令缺少 `PYTHONPATH=src` 失败，修正后完成；无 CPU 降级。
- 原始恢复达到15/25，seeds 1/2 为12/18、11/18。

## 33. 物种映射交叉验证与纠正

- recovered 计数交叉检查发现兔/羊映射互换，随后官方 FASTA 直接验证：ENSOCUT=兔、ENSOART=羊、ENSORLT=青鳉。旧映射把兔/羊/青鳉混淆，不能沿用。
- 修正并两次重算后，v3_all 和六个 split 均恢复为 25 个物种；`species_distribution.json` SHA256=`1a765a155da2e17b5cb2de50333682191c55758726091aa446d97ee3a4b5a13d`，`species_map.json` SHA256=`9ddab6c47fcb2f75aae36c231797df15978bfdda1b0119aef234257f68f66d38`。
- 更新 manifest SHA256=`fc84dd2f55f9ee62aa8cd2fde6034696c89492801281bc8bad2072ea17eb7b5c`。原始恢复17/25，seeds 1/2 为12/18、11/18。

## 34. 原始恢复失败修复与断点合并

- 22/25 manifest 记录犬 gzip 截断、anole 404、Ciona savignyi 404。官方目录核实正确文件为 `AnoCar2.0v2`、`CSAV2.0`，犬 URL 不变。
- 恢复器将重试前 `.tmp` 改为 `.truncated` 留证，并在重试时合并既有 manifest，避免仅 3 条新记录覆盖先前 22 条。
- 三个失败物种已并行重启恢复。完整回归 **154 passed, 1 skipped**。

## 35. seed1 长序列 OOM 与双 seed 限流

- `C41G7.2.1` 在 codonGPT 长序列批量 forward 时 OOM，完整错误显示其他项目也占用大量显存。保留已完成文件。
- seed1 进一步降为 workers=1，seed2 已为 workers=1；两条任务均单分片 GPU 运行，不用 CPU 替代。
- 原始恢复重试仍在进行，manifest 暂为 22/25，G0 未放行。

## 36. codonGPT micro-batch 修复长序列 OOM

- 单分片仍发生长序列 OOM，改为固定 16 样本 micro-batch，从内存机制上限制激活峰值。采样语义不变，真实 forward 按批次数累计，等效 token forward 不变。
- `C41G7.2.1` 真实 GPU 验证通过：100/100 唯一解、identity=1.0、forward=4,116、等效计算=58,800、34.91 秒。
- 两个 seed 已按断点恢复，不使用 CPU 替代。完整回归 **155 passed, 1 skipped**。

## 37. 当前 G0 裁决证据

- 修复 `a7_g0_gate.py` 在缺失 manifest/审计时的异常：缺失文件现记为失败证据，source/unique hash 写 `null`，不中断报告。
- 当前 `g0_gate_current.json`：full_distribution=true、frozen_assets=true、cuda_matmul=true、source_recovery=false、unique18_all_seeds=false，passed=false。
- 这确认 G0 未放行；seeds 1/2 与犬/anole 仍是直接阻塞。

## 38. 24/25 与犬 gzip 自恢复修复

- anole 已完成，manifest 更新为 24/25；仅剩犬 gzip 截断。
- 恢复器新增完整 gzip 解压校验，损坏 `.gz` 和对应 raw 改为 `.corrupt` 留证后重新下载，避免损坏文件导致反复失败。
- 新增损坏包契约测试，犬已按修复后的逻辑重启恢复。

## 39. 犬下载 Range 断点续传

- 下载临时文件已有合法 gzip 前缀时，恢复器使用 HTTP Range 从既有字节继续，避免网络慢时反复从头下载；非法前缀仍保留为 `.truncated`，服务器忽略 Range 时重写。
- 新增 Range 契约测试，共 4 项恢复测试通过。旧犬进程已停止并以断点续传方式恢复。
- seed1 当前15/18，seed2 12/18；原始 manifest 暂为24/25。

## 41. 25/25 原始来源验收通过

- `raw_release112/manifest.json` 已达到 25/25、`passed=true`、无失败记录，SHA256=`ae5a7fe88c82277533c916e6d359bec41cb10b5aa6265a03a1d71c58c18ad3c0`。
- 当前 G0 检查：full_distribution=true、frozen_assets=true、source_recovery=true、cuda_matmul=true、unique18_all_seeds=false；仅剩 seeds 1/2 独立复算未完成。
- seed1 当前17/18，seed2 12/18；主训练仍未启动。

## 42. seeds 1/2 全部生成完成，进入最终复算

- 两条 seed 均达到 **18/18 完整基因**，五方法全部 `done`。最后完成项包含 ENSACAT00000006494.4，持久化 GEMORNA 与 micro-batch codonGPT 正常运行。
- 已并行启动 seeds 1/2 独立 MFE/NED 复算，日志与 PID 写入 `unique18_seed{1,2}_recompute_final.{log,pid}`，不再使用自动 watcher。
- 复算完成后将运行 `a7_g0_gate.py`；当前原始来源 25/25 已通过，G0 只待这两项审计。

## 43. G0 正式通过与 D4 双臂训练启动

- seeds 1/2 独立复算均 18/18 全匹配；最终 `g0_gate.json passed=true`，所有检查项通过，SHA256=`8b5dbeea278c31792fb1a6107539c223cb9031a821d7152aee5f7e25d0ea136b`。
- 两条 56.8M `M_SYN_D4_FULL/EDIT_seed0` 从零启动，明确打印 synonymous corruption、train=621306、val=76444 和模型参数量，未使用旧 checkpoint。
- 实际 CUDA 并行：GPU 利用率 100%，约 16.5GB 显存；full-token 首步 loss 5.7661，edited-token 首步 loss 5.5690。训练持续至注册 plateau，不设步数上限。
- px2 最新代码完整回归 **159 passed, 1 skipped**。

## 44. PPT 第 46 页：G0 通过与训练启动

- 新增 PPT 第 46 页，记录 G0 全部通过、unique18 三 seed 全匹配、25 物种来源、56.8M 双臂和真实 CUDA 100% 利用率。
- 页面明确 G1 进行中、未收敛、未做 learned-vs-simple 裁决、预印本不可提交。

## 45. 首个训练进程中断与从零重启

- 两条首启训练在首个 epoch 中段进程消失，日志无 traceback、无 OOM，GPU 随后空闲；原因标记为外部中断，未臆测具体平台原因。
- 原目录无 best/last/training_state/converged，无法精确恢复。保留原日志，以 `M_SYN_D4_*_r2` 新 run ID 从零启动，不覆盖、不伪装 resume。
- r2 已重新使用 CUDA 运行，G0 与 synonymous corruption 不变。

## 46. 验证阶段 CUDA generator 设备修复与 r3

- r2 首个验证阶段失败：CPU generator 与 CUDA probs 不匹配；随后发现 `rand/randint` 也需直接在输入设备创建，不能只靠 `.to()`。
- 修复 `validate_packed` generator=device 以及 synonymous/arbitrary corruption 的随机张量设备参数。完整回归 **160 passed, 1 skipped**，直接 `CUDA_VALIDATE_PACKED_OK`。
- r2 无恢复状态，使用 r3 新 run ID 从零启动，保留失败日志与配置。
- 验证：46 页重开、关键文本、形状边界与 LibreOffice 渲染全部通过，临时文件已清理。

## 40. Gate 约束训练启动器

- 新增 `a7_run_training.py`：只有 `g0_gate passed=true`、train/val 哈希匹配、无旧 resume、无 epoch/step 上限且 CUDA 可用时才执行。
- `--dry-run` 仅打印冻结命令，便于 G0 后核对；未通过 Gate 时直接拒绝。契约测试覆盖命令保留与 Gate/哈希失败。
- 完整回归 **159 passed, 1 skipped**，主训练仍未启动。

## 47. 2026-11-13 r3 训练溯源与 G2 前置审查

- 两条 r3 训练仍在真实 CUDA 上运行，GPU 利用率采样为 100%；FULL 为 e1 b1100/17421、EDIT 为 e1 b2100/35442。均为首个 epoch 中间日志，不是收敛或性能证据。
- 训练机旧分支缺少 GitHub 的两个已验证提交，且修复和配置处于未提交状态。逐项比对源码、r3 配置和测试后，将相同内容正常提交、合并并推送，最终 commit=`6735cb3290400240ead5bc81f7e4f841d4978a8a`；没有 reset、强推、kill 或覆盖训练进程。
- r3 配置再次核验：FULL SHA256=`a6bcc4fe60ccfe082ebf126412bf9b0a46321c06a8eb8341f03a523df49142c6`，EDIT SHA256=`05ec5d8e850bf7a4f698f1c32935e57c975e647e337922da3d836c3cad95da94`。G0 哈希仍匹配。
- 启动 `07_a7_data/calibration_unique18/`：18 个开发基因，D4 train RSCU，seed=1729，n_uniform=40、n_per_axis=10；任务正在运行，尚未验收。该池只用于独立标定，不得由参评模型输出估计。
- G2 代码审查：目前只有 simple-search runner 和基础聚合器，尚无已验收的 learned G2 runner、完整配对检查和 G2 gate。正式 G2 仍未启动；不会将已有外部五方法或随机 smoke 冒充 learned 对照。
- 修订 spec/tasks/checklist/RECOVERY 中残留的 G0 未通过和 seeds 1/2 未完成状态；科学阈值不变。

## 48. G1 配对口径修复与 G2 执行工具准备

- 发现并修复 G1 把天然源序列误作 non-source 基准的问题：现在逐样本使用对应的随机 synonymous 初始序列；identity/legal 仍相对天然源验证。新增回归覆盖“未编辑但与天然源不同”的失败情况。
- G2 的 uniform 基线改为从同一 paired 初始状态进行独立单密码子同义替换，与其他方法共享操作符。calibration 显式保留原全局同义采样，保证冻结池生成方式不因基线修复而改变。
- 新增 `scripts/a7_run_learned.py`：真实 CUDA、冻结 checkpoint/hash、B=500 唯一 terminal scorer、base proposal、T=4、逐序列 identity、NED、HV anytime 和完整成本字段。simple/learned 使用同一 `seed*1009` 初始化函数；独立缓存避免跨方法预算泄漏。
- 两个 runner 均核对 calibration 的天然源 SHA256，结果增加 initial SHA256；G1 与 G2 的用途和输出严格区分。
- 本地完整回归 **164 passed, 1 skipped**。当前仍未训练收敛、未通过 G1、未运行正式 G2，也未形成模型性能结论。calibration_unique18 与两条训练继续运行。

## 49. G2 自动验收门与接口任务状态

- 新增 `a7_g2_gate.py`：要求每基因 seeds 0/1/2、learned 与四个 simple 方法完整，500 唯一 scorer，初始/源/benchmark/split/calibration/RSCU/commit 配对一致，identity=1，learned CUDA checkpoint 和 clean commit 可核验。
- 按主终点均值选择每基因最强 simple，再比较 learned/simple NED；18 基因下限、≥10% 中位改善、bootstrap 下界、跨双臂 Holm p 和 NED≥70% 共同裁决。缺失、partial、重复、未配对或错 checkpoint 均显式失败。
- 聚焦测试 **25 passed**，包括完整合成正例和多种拒绝反例；不是模型性能证据。
- `8e40307` 首次 GitHub 推送遇到 HTTP/2 framing 失败，第二次连接超时；代码已保存在本地与 `/home/codonflow`，但 GitHub 尚未确认同步，后续必须补推。
- 随机 checkpoint learned CUDA 接口任务仍在运行，尚无结果 JSON，不标记通过。development calibration 最新完成14/18；正式训练继续，G1/G2 均未通过。

## 50. development calibration 验收与 learned 批量推理

- `calibration_unique18` 已完成18/18，全部 `done`。逐文件 reference/pool SHA、天然源、D4 train RSCU、seed=1729、40 uniform+每轴10、全部 runs、正有限 scale 均通过。
- `07_a7_data/calibration_unique18_acceptance.json`：passed=true，SHA256=`e84a133c0c58df8d59adc62c47df7eb249b12ec969b76924c6ad41b2f419407c`。
- 独立重新运行 C31E10.3b.1 calibration，reference 与 pool 均与冻结文件逐字节一致（69 唯一目标向量）；产物保存在 `calibration_unique18_independent_recheck/`。显式 global-synonymous calibration 模式保持了旧池生成语义。
- learned 推理从逐路径 forward 改为同长度路径批量 forward，仍使用原 `SynonymousJumpProposal.sample_transition_batch` 和 base kernel，不引入 terminal guidance 或 rollout。每条路径、每个状态转移及实际 batch forward 分开计费；唯一 terminal scorer 预算不变。
- 批量化后完整回归 **170 passed, 1 skipped**；尚未完成真实 CUDA 批量接口验证，不得写成性能或科学结果。原串行随机接口任务保留日志，不覆盖输出。

## 51. 收敛审计器与 GPU 接口证据

- 新增 `a7_convergence_audit.py`：只有完整 checkpoint、连续 log epoch、三 epoch <0.1% plateau、best/last/training_state/converged、优化器/CUDA RNG、数据/配置/commit 一致时才生成通过清单。
- 四个 checkpoint 均须可加载；在 CUDA 上加载每种权重、执行有限前向并同步，另核对 converged 与 best 张量逐项一致。禁止 CPU 降级和 `/home` 大型权重输出。
- 历史、继续显著改善、日志不一致和错误 best epoch 的4项聚焦测试通过。正式模型尚未完成首个 epoch，因此该工具没有实际通过记录。
- 两个随机接口进程均已确认占用 CUDA 显存，GPU 利用率采样100%；尚无最终 JSON，不能写成接口验收通过。批量任务等待器保留，后续以产物为准。
- `f6bfaad` 的 GitHub push 再次失败；训练机 bundle 同步已完成，远端主干仍为 `5796bf4`，后续补推。

## 52. G2 严格断点与天然源元数据修复

- 修复 simple payload 把 paired 初始序列哈希写入 `source_sha256` 的问题；现在与 learned 一样记录天然源 SHA，初始序列另存 `initial_sha256`。Gate 会拒绝任何旧的不一致结果。
- simple/learned 均支持 `--resume`，默认拒绝覆盖已有结果；只有 done、clean、record/seed/method/source/initial/calibration/RSCU/checkpoint/commit 全匹配才跳过，不静默忽略错误或缺失。
- 新增3项 resume 契约测试；与 G2、learned 合计10项聚焦测试通过，完整回归 **177 passed, 1 skipped**。
- 随机串行和批量接口尚未生成结果 JSON，不能声称提速或通过；当前正式训练仍在进行，G1/G2 未启动科学验收。

## 53. learned 串行接口完成与 base 批量向量化

- 原串行随机 checkpoint 接口完成：500 唯一 terminal scorer、515 paths、2060 base state evaluations/forwards、1417.836秒，identity=1、CUDA、clean commit。产物 SHA256=`76e9d1ca3f544bf438be4826407218fd1d93a1f3279380519f9fcc03d9401b37`。这是随机权重工程验证，不是 G1/G2 科学结果。
- 原批量接口已运行超过10分钟，尚无 JSON；simple 四方法接口已启动，尚无完成输出。均不以进程存在冒充完成。
- 审查发现批量版本仍逐状态、逐位置执行局部 log-softmax。已将 `sample_transition_batch` 改为按位置对整个 batch 向量化，候选顺序、显式 stay 和采样 RNG 与原实现一致，Transformer forward 数不变。
- 同 RNG 回归要求转移/位置完全一致，log probability 在1e-12内一致；不同张量形状归约导致的约4e-16差异已明确记录。完整回归 **177 passed, 1 skipped**。新向量化的真实 CUDA 与500预算接口仍待验证。

## 54. G2 uniform 协议澄清与 partial 留证（正式结果前）

- 工程接口中，单密码子 independent uniform 在 C31E10.3b.1 达到25,000 attempts 后未凑齐500唯一序列，脚本因 `max_attempts_exhausted` 不在结果 schema 而未保存 JSON。该基因534nt，完整同义空间极大，不是空间不足。
- 纠正此前对“同操作符”的过窄解释：G2 保留更强的**全局逐位置独立均匀同义采样**作为 uniform；hill/MH/AReUReDi/learned 仍使用单密码子局部核。所有方法首次评分均为同一 paired 初始状态，scorer/cache、预算、校准与 Gate 阈值不变。这是正式 learned 结果前的基线修正，避免用弱 uniform 降低对照强度。
- `a7_protocol.json`、spec/checklist/runbook 同步上述定义；calibration 生成方式不变。单密码子 uniform 仅保留可选消融，不替代强 uniform。
- simple runner 把非 done 映射为 `partial`，记录 `incomplete_reason` 并保存 JSON；G2 Gate 仍明确拒绝。失败日志 `g2_interface_simple/run.log` 保留，不覆盖旧目录。
- 新增全局/局部 uniform 回归，相关36项测试通过。旧批量与向量化 learned 接口尚无最终 JSON，simple 修正版尚待独立重跑。

## 55. 向量化 learned 接口验收与冗余 smoke 取消

- `g2_interface_smoke_random_vectorized/C31E10.3b.1_learned_s0.json`：500唯一评分、515 paths、2060 base transitions、68 batch forwards、451.945秒；SHA256=`9609e0fba4b9c68d65348d7bb0242881c18a64cecb15fb168b6552542a452cff`。
- 独立重算 AUC、逐序列 protein identity、唯一数、schema、CUDA 与 clean commit 全部通过。相对串行加速 **3.137185×**，`g2_interface_learned_acceptance.json` SHA256=`890688b033af9366bf12474ea0c4f386d94c5792012eebb2fd9d8bf62cd76b41`。这是随机权重工程接口验收，不是科学 Gate 或模型性能。
- 原非向量化 batch 任务在产生结果前被取代，已只终止该冗余 smoke PID 82341，保留日志与 `g2_interface_smoke_random_batched/cancelled.json`；未触碰两条正式训练或其他项目进程。
- `4e003e8` 已成功推送 GitHub；强 uniform 和 partial 修正版 simple v2 正在运行，尚无完成结果。正式模型仍处 P2/G1。

## 56. uniform 接口交叉核验与 G1 stop 修正

- `g2_interface_simple_v2/C31E10.3b.1_uniform_s0.json` 已完成：全局 uniform、500唯一解、identity=1、178.088秒，SHA256=`5d6782c11410f6e00dc351cd3423f478245e66ccd1a7b667021c75de389d4140`。
- 其天然源 SHA 与 learned 一致且不同于 initial SHA；paired initial SHA 与 learned 完全一致；schema 和冻结 calibration 的 AUC 重算通过。其余 simple 方法仍在运行。
- 修复 G1 uniform 诊断包含终端 stop 索引的问题；现在仅在前 `len(codons)-1` 个可编辑位置抽样，保留当前密码子作为 stay 可能性。100个 seed 的 stop 保持回归已加入。
- 以上仍是工程验证，没有新训练收敛、G1或G2科学结论。

## 57. simple 四方法接口验收与 G2 preflight

- C31E10.3b.1 的全局 uniform、hill、MH、AReUReDi-style 均完成500唯一解、identity=1、clean commit、零模型 forward。耗时依次178.088/181.124/191.734/165.615秒，初始SHA与天然源SHA全组一致。
- 首次后台验收脚本的嵌套 f-string 引号错误已留证；它发生在实验完成后，只影响验收脚本。改用显式方法列表的独立核验后，四份结果均通过，`g2_interface_simple_v2/acceptance.json` SHA256=`ab3c90d2afe1faa87105e78a33f035d9790e910c7db50f7ccae247ffd06f58d3`。这些是工程数字，不是 learned-vs-simple 结论。
- 新增 `a7_g2_preflight.py`：绑定收敛审计、对应G1、不可变checkpoint、CUDA证据、至少18开发基因、calibration/source/RSCU和clean commit；输出 `ready_for_g2=true` 但 `scientific_gate_passed=false`，避免把启动许可误写成科学通过。
- preflight 合成正例和checkpoint不匹配反例通过。正式D4模型仍未收敛，G1/G2未启动科学验收。

## 58. G1 收敛后自动验收监视器

- 新增 `a7_follow_g1.py`：仅轮询训练产物和 launcher PID，不频繁读取 GPU 显存；只有 `converged.json` 出现后才运行 CUDA 收敛审计、三基因×100样本G1和G2 preflight。
- 进程无收敛产物即结束、PID命令不匹配、审计失败或G1未通过均停止并写 `status=failed` 与 traceback；不自动重启、不覆盖历史状态、不自动启动G2。
- 产物分臂保存在 `/teams`，包含配置/审计/G1/preflight哈希及独立命令日志。完成状态仅为 `g1_passed_g2_preflight_ready`，`scientific_gate_passed` 仍由实际G2决定。
- 配置、PID命令匹配和失败日志3项测试通过。监视器尚未部署启动，正式训练仍在进行。

## 59. G1 监视器实际启动

- `/home/codonflow` 与 GitHub 已同步 `7ab3cb819a974cfcd65ff3449db348f3dfcac76c`，本地/训练机完整回归 **184 passed, 1 skipped**。
- 监视器已启动，状态 `waiting_for_convergence`；状态文件 `07_a7_data/g1_r3_watcher/status.json`，启动日志 `launch.log`，PID 文件 `watcher.pid`。
- FULL/EDIT 配置SHA分别为 `a6bcc4fe…`、`05ec5d8e…`，与 r3 一致；G1 固定 C31E10.3b.1/C14A6.7.1/C01H6.8b.1、100 paired samples、T=4。
- 监视器只在真实收敛后审计并进入 G1，G2 preflight 输出仅作启动许可；当前没有新的模型验收或性能结果。

## 60. 预印本方法与评价协议工作稿复核

- 更新 `paper/CodonFlow_preprint_A7.md`，明确 G1 non-source 相对 randomized paired initial，identity/legal 相对天然源；uniform 为强全局逐位置同义采样，局部搜索/learned 为单密码子核。
- 补齐56.8M架构、AdamW、60k有效token、独立验证seed、T=4、batch32 base无guidance/rollout、独立cache和完整成本计数。
- 写入40 uniform+四轴×10 calibration、reference/scale公式、3 seeds初始化、最强simple按基因3-seed均值AUC选择、bootstrap/Wilcoxon/Holm及NED采样规则。
- G2明确18基因、双臂、500唯一评分、≥10%改善、CI、p和NED≥70%。Results/Abstract/Discussion仍为Gate占位，没有加入训练中间loss或接口AUC作为科学结论。
- 当前仍是不可提交的工作稿；只完成方法/协议部分，不代表预印本已经完整。

## 61. G2 正式分片执行器与 dry-run

- 新增 `a7_execute_g2.py`：必须同时提供 FULL/EDIT preflight，核对输出根目录、G1/审计/配置/checkpoint/RSCU哈希、共同benchmark/records/seeds/协议及clean commit。
- 每臂18基因×3 seeds，共108 learned shards；四方法shared simple共54 shards，不为两臂重复计算。simple-workers=4、learned-workers=2并行，只有所有结果done/identity=1/500唯一解后才运行G2 Gate。
- learned 非done现在保存partial及原因，不能进入统计。resume保留previous_status，每次attempt使用独立日志，不覆盖失败记录。
- `a7_g2_gate.py` 支持同一arm同时传learned/simple glob，避免把shared simple误作独立臂。相关10项测试通过；完整回归 **187 passed, 1 skipped**，GitHub/训练机同步 `3064f3c`。
- 首次synthetic dry-run命令的嵌套引号失败已修正；重跑确认108+54=162任务，`scientific_gate_passed=false`。产物在 `g2_executor_dry_run/`，明确不是启动证据，未执行正式G2。

## 62. G2 中心图生成器与临时渲染检查

- 新增 `a7_plot_g2.py`：读取冻结 `a7_g2_gate_v1` 及原始JSON，逐个核对SHA、done与identity，重建双臂 anytime 曲线和基因级效应CI；输出PDF、PNG、逐基因CSV与manifest。
- 标题直接按真实Gate标记Go/No-Go，曲线含50/100/500预算网格，保留每基因最强simple及NED/统计注释，不删负结果。
- 合成fixture已补齐真实曲线网格；测试验证PDF/PNG magic、36行逐基因表和manifest。完整回归 **188 passed, 1 skipped**。
- 通过临时本地HTTP实际检查测试图的三面板、图例、阈值线和文字布局，随后关闭页面/服务并删除图片。合成图不进入PPT或论文，真实G1/G2仍未完成。

## 63. G2 证据门后续监视器

- 新增 `a7_follow_g2.py`：等待 `g1_r3_watcher/status.json` 明确为 `g1_passed_g2_preflight_ready`，核验双臂 preflight 哈希后才执行 dry-run。
- dry-run 必须得到108 learned+54 shared simple，随后运行正式分片器、G2 Gate和冻结JSON图形生成；最终状态只读取真实 `scientific_gate_passed`，不自动进入G3。
- G1失败、监视器提前退出、preflight变动、任务数异常或执行失败均记录failed和traceback，不覆盖旧状态。
- 3项等待/双preflight/失败停止测试通过。正式训练与G1仍在进行，G2尚未启动。

## 64. G2 等待器实际启动与连接恢复

- `6bbee52c88d885cca338dfb95ddc1243854fe3a2` 已推送GitHub并同步训练机，本地/训练机完整回归 **191 passed, 1 skipped**。
- bundle复制及G2等待器首次启动分别遇到一次远端SSH关闭；重连后先确认训练日志仍推进、`g2_r3_watcher/status.json` 不存在，再启动，未盲目重复提交。
- 当前 `07_a7_data/g2_r3_watcher/status.json` 为 `waiting_for_g1_preflights`，`scientific_gate_passed=false`。只有两臂G1和preflight均通过才会自动dry-run及运行162分片。
- 两条正式训练仍在首个epoch，尚无收敛或G1结果；自动流程没有提前越过Gate。

## 65. 离散流相关工作的原始出处核验

- 本地AutoGLM token服务不可用，改用公开arXiv页面及官方API元数据，逐条核对标题、作者、年份和方法边界，不凭记忆补写书目。
- pCoMole：`arXiv:2610.01663`，Chen/Holsman/Zhao/Chatterjee，2026；terminal feasibility、augmented Tchebycheff、Doob-h与短MC rollout，NeurIPS 2026。
- AReUReDi：`arXiv:2510.00352`，Chen/Zhang/Chatterjee，2025；Tchebycheff、locally balanced proposals与annealed MH。
- MOG-DFM：`arXiv:2505.07086`，Chen/Zhang/Tang/Chatterjee，2025；hybrid rank-directional score与adaptive hypercone filter。
- TR2-D2：`arXiv:2509.25171`，Tang/Zhu/Tao/Chatterjee，2025；树搜索replay buffer和trajectory-aware fine-tuning。
- Related Work与References已加入这4条原始出处，明确我们的AReUReDi-style只是内部同义搜索对照，不是官方复现。其他文献继续核验，Results保持空白。

## 66. 外部 baseline 与全长 mRNA 文献核验

- LinearDesign：Zhang et al., Nature 2023，DOI=`10.1038/s41586-023-06127-z`，原始预印本 `arXiv:2004.10177`；此前错误DOI后缀未写入。
- codonGPT：Binita Rajbanshi、Anuj Guruacharya，NAR 2025，`10.1093/nar/gkaf1345`。
- GEMORNA：Zhang et al., Science 2025，`10.1126/science.adr8470`。
- mRNAutilus `arXiv:2605.31296`、ProMORNA `arXiv:2605.01513`、mRNA-GPT `10.64898/2026.03.31.715707` 均核实为全长mRNA任务，不与CDS-only warm-start混比。
- RayGun `10.1038/s41586-026-10842-8` 与SCISOR `arXiv:2511.07390` 为蛋白缩小/删除任务，维持数值表排除。
- 经Crossref全名复核，纠正作者首字母：Rajbanshi=B、Devkota=K、Shonai=D、Mao=J；未保留猜测缩写。参考文献共12条，任务边界与原始摘要一致。
- `a7_baseline_resources.json` 已更新三seed复核状态、3份独立复算报告SHA及LinearDesign出处。没有将外部摘要指标写为CodonFlow结果。

## 67. G2 Gate v2：原始证据独立重算

- `a7_g2_gate.py` 升级为 `a7_g2_gate_v2`：正式CLI强制benchmark与calibration路径，重 reconstruct paired initial、逐序列identity、500唯一解、calibration来源/RSCU/SHA、NED与anytime AUC。
- 增加跨基因及跨臂 benchmark/RSCU/split/code_commit一致性检查，禁止仅信任runner自报identity/NED/AUC。执行器已传入必需路径，绘图仅接受v2并记录raw重算标志。
- 合法fixture使用五个不同密码子位置的四进制编码产生500唯一同义序列；先前重叠导致324唯一的问题已修正，没有降低唯一性阈值。
- 正向重算与initial/identity/AUC/NED篡改反例共12项测试通过；包含calibration角色检查的完整回归 **196 passed, 1 skipped**。
- 论文方法同步写明原始指标重算。以上仍是验证工具，不是G2结果；两条正式训练仍未收敛。

## 68. r3 首个验证阶段双臂失败与修复

- FULL 在 `conditionality_probe` 失败，traceback 明确为两个默认 CPU generator；独立 val 已执行但未写 epoch 日志或 checkpoint。probe 已改为 device generator，并与训练臂使用同一 corruption 类型。
- EDIT 在独立 val forward 中 OOM：进程上限0.30=9.41GB，需额外2.06GB时物理显存尚有12.69GB空闲，属于人为上限而非物理耗尽。保持val_batch_tokens=24000及验证聚合不变，r4 EDIT cap调至0.42；FULL cap仍为0.35。
- r3 两臂均无 best/last/training_state/converged，不能精确resume。G1/G2 watcher均记录failed并停止，未进入下一阶段。
- r4 使用全新run ID和输出目录从零启动；不覆盖r3日志，不伪造恢复，不跳过验证或保存伪checkpoint。

## 69. 验证显存问题的等价 micro-batch 修复

- r4 EDIT cap从0.30升至0.42后，直接全量CUDA验证仍在首个长batch OOM，尽管当时约29GB空闲；不能靠继续放大上限解决注意力峰值。
- `validate_packed` 保留原24000-token batch及一次完整batch腐蚀，再按4000 tokens分micro forward。BCE和token loss分别按各自有效位置数还原，不能用两个权重之和作分母。两种目标下full/micro loss一致，6项probe/验证聚焦测试通过。
- r4 显式加入 `val_micro_batch_tokens=4000`，原val batch/数据/RNG/聚合语义不变。r3无checkpoint，仍需新run ID从零重启；r4尚未启动。
- 首个直接验证OOM已保留失败证据，未写伪val或伪收敛结果。

## 70. r4 全量 CUDA 验证通过与双臂启动

- 逐 batch CUDA 调试最终1800/1800通过，正式 `validate_packed` 单次全量调用也通过：76444条独立val、1800原batch、val_micro_batch_tokens=4000、synonymous corruption，loss和cond gap均有限。
- `07_a7_data/r4_cuda_validation.json` passed=true，SHA256=`9ce613b92d62cb3fb198e85fc6cacb3559036b564fcd41df27d10421614777f6`。仅工程验证，不是训练收敛或性能结果。
- 本地与训练机完整回归 **200 passed, 1 skipped**，代码commit=`1f38db6f35735326917e106c95ce61a3f17abe27`。
- r4 FULL/EDIT已从零启动，配置SHA分别为 `4704a062c24a0e35fd870b327a64e9c45f862a0547f8a3440d6c3083915748ee`、`91290185230488a767162b17ec38f901bf81ef7266c18fa8e92384a068b2c41d`。
- `g1_r4_watcher` 与 `g2_r4_watcher` 均处于等待状态；r3 watcher failed状态保留，不覆盖。当前没有有效checkpoint，G1/G2未放行。

## 71. r4 训练进行中与 GitHub 推送恢复

- r4 FULL/EDIT 均正常进入训练批次，配置SHA与冻结r4一致，G1/G2 watcher保持等待，无CPU降级或新异常；尚无首个epoch的val/checkpoint。
- GitHub多次HTTP/2、连接超时和空回复后，使用 `http.ipVersion=ipv4` + HTTP/1.1 成功正常推送。官方 `gh` API 二次核实远端main SHA=`39f0520bdc793499c223291e40dc2f69135ba983`，本地与远端一致。
- 未使用API重写历史或强推。后续Git操作优先使用已验证的IPv4通道，连接失败时不误报已上传。

## 72. 收敛配置完整性审计与 micro-forward 文档同步

- `a7_convergence_audit.py` 新增 `validate_run_config`，除模型/数据外，还核对 batch_tokens、max_batch、grad_accum、grad_clip、val_batch_tokens、val_micro_batch_tokens、lr、wd和gpu_mem_fraction，防止只验证部分协议。
- 新增 micro-batch 不一致反例测试。恢复指南已改为r4真实状态，论文明确原batch一次腐蚀、4000-token micro-forward、BCE/token分别按有效位置还原，不改变验证定义。
- r4继续正常训练，尚无收敛结果。文档更新不代表G1通过。

## 73. GitHub SSH 正常推送恢复

- 普通HTTPS长期失败后，GitHub SSH认证实测可用，使用同一仓库SSH地址正常fast-forward推送，远端main SHA=`b9edbe13a719d21f6af430a4fdd1877394602e5a`，经 `gh` API核实。
- 先前API对象同步路径因blob/tree SHA校验失败而停止，未更新远端引用；最终未采用该路径。没有强推或改写历史。
- r4 FULL/EDIT持续真实CUDA训练，训练loss仍下降，尚未完成首个epoch或产生收敛/G1证据。
