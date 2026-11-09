# 发布签名与初始信任

程序包和知识包各有独立版本。发布索引及包内清单均用 Ed25519 签名，使用 cryptography 的实现；签名绑定通道、版本、目标平台、负载大小／哈希及每个文件。校验先验证本机已信任的公钥，再检查负载和文件清单。包内的公钥不能自行取得信任。文件哈希用于完整性，发布身份来自预先固定的公钥。

生产身份由 `tools/p6/create_signing_identity.py` 在 `.local/signing/` 新建。私钥用当前 Windows 用户的 DPAPI 加密，不进入源码、wheel、安装包或诊断导出；公钥可独立分发。构建不自动上传，不自动轮换身份。DPAPI 文件需与用户配置一同妥善备份，丢失身份后的密钥轮换需要独立可信渠道重新固定公钥。

`--test-signing` 只产生带 `.TEST` 名称和 `channel=test` 的包。生产默认拒绝测试身份；测试还须明确传入本机测试信任和 `allow_test`，不能由网络包请求启用。正式候选可以由本地生产身份签名，但不意味着已对外发布或完成 Windows／宿主验收。

首次安装的脚本与公钥应从玩家认可的源码／维护者渠道取得。候选介质提供固定指纹的引导运行时，首次执行前核对引导指纹；随后仍须验证程序包的发布签名。不能把同一不可信下载页上的任意哈希或公钥当成身份凭据。现有安装的更新器只使用本机固定身份，网络资料和 MCP 参数不能改写信任配置。本项目尚未提供 Windows Authenticode 或 SmartScreen 信誉。

运行时来自 [Python 官方 3.12.10 页面](https://www.python.org/downloads/release/python-31210/)中的 Windows x64 嵌入包，具体来源、下载哈希与全部运行文件在 `manifests/windows-runtime.lock.json`；此版本是本轮兼容基线，未宣称最新安全补丁版本。依赖只使用 `requirements-runtime.lock` 中锁定的二进制分发物。P0 的完整 HSR_Nous 环境不是安装包内容；简化比较和四模式模板不依赖它。

签名 API 依据 [cryptography Ed25519 文档](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/)。校验器不防御能修改同一 OS 用户下程序、信任文件或数据库的恶意进程。
