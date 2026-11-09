# 第三方组件与来源

原创部分保留所有权利。以下清单依据本轮实际锁定的 Windows x64 运行文件及各 wheel 的 METADATA／licenses 目录，不以知识参考来源的许可证替代可执行组件许可证。构建保留每个分发包的许可证及版权声明。

| 实际组件 | 版本 | 分发声明 | 随包位置 |
|---|---|---|---|
| CPython Windows x64 嵌入包 | 3.12.10 | PSF 及发行物内第三方声明 | runtime/LICENSE.txt |
| attrs | 26.1.0 | MIT | runtime/Lib/site-packages/attrs-26.1.0.dist-info/licenses/LICENSE |
| cffi | 2.1.1 | MIT-0 | runtime/Lib/site-packages/cffi-2.1.1.dist-info/licenses/LICENSE |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause | runtime/Lib/site-packages/cryptography-50.0.2.dist-info/licenses/ |
| jsonschema | 4.26.0 | MIT | runtime/Lib/site-packages/jsonschema-4.26.0.dist-info/licenses/COPYING |
| jsonschema-specifications | 2025.9.1 | MIT | runtime/Lib/site-packages/jsonschema_specifications-2025.9.1.dist-info/licenses/COPYING |
| pycparser | 3.12 | BSD-3-Clause | runtime/Lib/site-packages/pycparser-3.12.dist-info/licenses/LICENSE |
| referencing | 0.37.0 | MIT | runtime/Lib/site-packages/referencing-0.37.0.dist-info/licenses/COPYING |
| rpds-py | 2026.9.1 | MIT | runtime/Lib/site-packages/rpds_py-2026.9.1.dist-info/licenses/LICENSE |
| typing_extensions | 4.16.0 | PSF-2.0 | runtime/Lib/site-packages/typing_extensions-4.16.0.dist-info/licenses/LICENSE |

Python 官方嵌入包和 cryptography 二进制还包含各自声明的原生组件，包括 OpenSSL；Python 发行物含 Windows C 运行时。保留原发行物提供的文件及许可证，不将它们改标为本项目原创。精确输入、大小和 SHA-256 见 manifests/windows-runtime.lock.json 与 requirements-runtime.lock。

HSR_Nous 固定 commit f8935ddb407b297732fbd3c624d55897e3e648b9，原许可 MIT；许可证副本为 HSR_Nous-MIT.txt。它的完整后端、游戏数据与本地补丁验证环境未打进玩家安装包，属于可选独立环境；简化比较不需要它。原始社区知识库、角色数据仓库和网页不整体转发，知识包只含本项目整理的32条起始内容和来源引用，具体适用版本及来源见各知识条目和 knowledge/sources.json。

构建工具 hatchling、editables、pytest、uv 只用于开发构建，不纳入玩家运行时。测试和诊断不会把开发者凭据、私人 UID 资料或研究正文分发给玩家。
