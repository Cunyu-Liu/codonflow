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
