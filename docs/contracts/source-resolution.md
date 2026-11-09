# 来源、证据和缓存

公开知识包与个人证据隔离。`evidence_register` 将具体论点、URL、观察日期、适用版本、内容 SHA-256、资料种类、立场和转载依赖保存在指定账号的 SQLite 中。`host_search` 只标为 search_summary；`host_page` 标为 reported_page，不冒充本连接器独立抓取。网页中的任何指令都只是 data_only 内容。

`evidence_resolve` 返回支持与反对的资料，保留相同论点的不同立场。根来源集合有交集的转载链归为一个来源组；两篇转载不算两份独立证据。未登记的转载关系无法自动推断，调用者应登记原始 URL 或 depends_on；不把来源数量当作真伪表决。

`source_fetch` 只实现已选公开来源连接器：raw.githubusercontent.com、github.com、static.nanoka.cc、米游社／HoYoLAB。其他公开网站由宿主搜索／获取后登记，避免假称实现了任意网页解析。只允许公开 HTTPS，无 Cookie、无凭据、无重定向、无自动重试，响应限额 2 MiB、超时 8 秒；不接入任何 UID 地址。响应格式变化和空正文显式失败。

缓存位于 data-dir/sources，以 URL 哈希命名，并校验正文指纹。过期、离线或联网失败时可返回原日期缓存，状态 partial、stale 和 network_failure 明确，不能称为最新。正文按字符分页。来源可用只证明获得资料，不证明论点正确或完整游戏机制已验证。

SQLite v2 为证据、UID 动作和研究修订新增表；首次写入事务迁移，保留 v1 账号、快照和 Markdown。只读旧数据不强制迁移。
