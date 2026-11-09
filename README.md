# 星穹铁道 AI 玩家助手

Windows 本地助手，接入你已有的 Codex，提供机制研究、双账号私人记忆、固定状态计算、四模式简化比较和抽卡预算规划。数值计算在本地完成，不另接模型服务。当前候选版本 **0.1.3**，项目保留所有权利。

P6 候选正在验收：50个中文真实宿主案例及针对问题的复测已完成，发布关口以 [P6记录](docs/gates/P6-release-candidate.md) 为准。当前只验收 Codex；DSH、Claude Code 暂缓。覆盖范围见 [coverage](docs/coverage.md)，不会把固定窗口伤害说成游戏得分、通关概率或你的账号收益。

## 安装到玩家项目

先安装并登录 Codex。候选介质自带项目内 Python，无需全局 Python、uv、Docker 或管理员安装。

从本仓库固定一个提交，取得 `install/windows-x64/` 的完整文件夹，然后运行：

```powershell
& '.\install\windows-x64\Install-HSR.ps1' -Workspace 'D:\HSR 玩家项目'
```

明确离线使用时加 `-Offline`。安装器保留项目原有配置，生成项目级 MCP、共同规则、三个技能及 `.hsr-companion/打开助手.ps1`。用该入口进入项目后正常交流，首次只补缺失的风格、区服或账号信息；可以先手工研究，不强制提供 UID。给 Agent 的完整安装提示词见 [INSTALL_AGENT](INSTALL_AGENT.md)。

首次下载的脚本与公钥须来自你认可的项目来源；脚本先核对引导介质与固定公钥，程序再检查发布签名和文件清单。不能把下载页上任意自报哈希当发布身份。详见 [签名说明](docs/release/signing.md)。本项目没有 Authenticode／SmartScreen 信誉声明。

## 日常使用

可以直接问：“行动提前与加速有什么区别”“找回上次的配队研究”“比较这个固定窗口的两个配置”“我该抽角色、光锥还是不抽”。定量输入不足会列缺项，不用内置例子冒充你的持有和练度。

公开 UID 只在明确要求导入／刷新时查询。展示页不是完整背包，未展示不代表未持有；星琼、票和保底需要手工资料。启动、TTL 到期和知识更新都不会自动刷新账号。

32条起始知识、公开来源引用、账号隔离、研究冲突待确认、保存输入重算均已实现。四模式使用少量指定技能、E0且无大行迹的假设窗口；完整战斗后端是可选独立环境，未包含在玩家包中。当前期数需要区服与排期证据，不足时明确使用历史／通用条件。

## 更新与恢复

程序包与知识包独立签名、独立版本。初装可写入签名包绑定的维护者来源，已有玩家配置不会被覆盖。知识兼容更新可自动同步；程序只提出绑定版本／指纹／路径的方案，已有匹配的一次性确认才安装。当前业务确认通过本地交互终端 `confirm-update`，模型不能自行代答。

升级先暂存、自检和备份，再切换不可变版本；运行中的旧依赖保留。中断后用同一介质恢复，回滚先验证原快照和当前资料兼容性：

```powershell
& '.\install\windows-x64\Install-HSR.ps1' -Workspace 'D:\HSR 玩家项目' -Action recover
& '.\install\windows-x64\Install-HSR.ps1' -Workspace 'D:\HSR 玩家项目' -Action rollback
```

有已保留的受管程序快照时，旧实验可以用原代码、原输入离线重算；没有原快照就拒绝冒充相同规则。不是中途战斗的断点续算。

## 卸载与排障

先退出占用该安装的 Codex 会话，再从候选介质执行：

```powershell
& '.\install\windows-x64\Install-HSR.ps1' -Workspace 'D:\HSR 玩家项目' -Action uninstall
```

默认保留账号、研究与实验，清理受管 MCP／规则且保留玩家自写内容。独立添加 `-PurgeData` 才会把个人目录改名隔离，仍可手工恢复；安装备份也可能包含个人数据库。

让 Agent 查 `local_help` 可取得实际命令。默认诊断先生成待分享清单，排除 UID、研究正文、凭据和本机路径，审阅后才导出本地 ZIP，不自动上传。详见 [排障](docs/troubleshooting.md)、[隐私](docs/privacy.md)、[安全边界](docs/security-boundaries.md)、[Windows矩阵](docs/validation/windows-install-matrix.md)。

## 开发与贡献

开发环境要求 Python 3.12。哈希锁定依赖、测试说明与机制贡献要求见 [CONTRIBUTING](CONTRIBUTING.md)。本项目不是官方产品，原创部分尚未开放授权；第三方材料见 [LICENSE](LICENSE) 与 [第三方清单](licenses/THIRD_PARTY_NOTICES.md)。
