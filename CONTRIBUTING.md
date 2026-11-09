# 贡献与开发验证

原创项目暂不开放授权。提出问题、提交机制资料或代码前，请标明作者、原始来源、适用游戏版本、许可及允许分发的范围；许可不明的材料不纳入候选。不要上传真实 UID 响应、账号快照、私人研究、Cookie、凭据、签名私钥或完整模型轨迹。

机制修订需要可复核的论点、来源正文日期、支持与反对证据、明确假设和最小复现输入。转载应标记原始来源依赖，不能按转载次数投票。未上线资料与正式服分开，不能把简化窗口结果改写成精确游戏分数。

Python 3.12 开发环境：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-deps --no-build-isolation -e .
.\.venv\Scripts\python.exe -m pytest tests/calculators tests/memory tests/install tests/release tests/security tests/planning tests/modes tests/transport -q -ra
```

默认测试禁止外网。真实 UID 测试只在提供专用测试输入并明确 `--run-live` 时运行。完整维护者回归另依赖本机 `.local` 中已冻结的可选旧后端和原验收输入，不能把干净检出缺少该可选环境说成默认玩家安装失败。

构建者可用 `tools/p6/prepare_inputs.py --uv <已有uv程序>` 准备官方运行时与锁定二进制依赖，再用 `tools/build_release.py --test-signing --output <测试目录>` 构建带 TEST 标签的包。生产校验器不信任测试密钥；生产身份在本机通过 DPAPI 保护，不入库。知识使用 `tools/build_knowledge_release.py` 独立构建。具体输入和签名链见 docs/release/signing.md。

真实模型验收会使用现有模型渠道和额度，须由操作者明确运行。`tools/p6/verify_codex.py --prepare --artifact <已签名候选> --model <已获准模型> --reasoning <配置>` 准备隔离项目；随后按冻结案例运行。原始证据放 .local，公开只保留去敏摘要。保留首次失败，修复后复测相关用例，不调整断言掩盖缺陷。
