# 旧项目迁移指南

本轮是模板升级，不是覆盖已有业务仓库或执行生产发布的脚本。请在旧项目自己的分支按能力合并，并在可销毁副本演练后再安排发布。

## 1. 升级前记录

备份 PostgreSQL 与 Redis，记录当前 Alembic revision、用户名/手机号唯一约束、cellphone 非空约束、用户数及密码哈希种类。不要导出明文密码、原始 token 或验证码。

检查旧用户数据：

- 新用户名规则以外的长度/字符/首尾空白，仅报告，不自动改名、lower、strip 或删除
- 某用户 username 等于另一用户 cellphone 的跨列碰撞，包括历史已删除记录
- 重复或非规范手机号、昵称超出持久化上限、旧项目自己的 enum/trigger/列变更
- 不符合升级条件的数据由业务方人工处理，不生成虚假手机号、不静默合并身份

新注册用户名禁用手机号形态，不能自动解决旧碰撞。密码登录遇到两个不同历史身份匹配时统一 401，不按查询顺序、密码或账号状态选择其一；同一个用户被两个条件命中仍只有一个身份。已有旧格式用户名可按原文登录，新的注册格式不能套在登录/用户响应上。

## 2. Python 与依赖

- Python 最低 3.13，默认 3.14；创建本项目 `.venv`，用 `uv sync --locked`，不继续借用旧 Conda 环境
- 三份 requirements 被 pyproject/uv.lock 替代；确需 pip 时从 lock 导出，不维护两套手工清单
- JWT 切换 PyJWT，新密码切换 pwdlib/Argon2；旧 bcrypt 仅保留读取兼容
- fastapi-limiter 被 limits 的异步 Redis 固定窗口替代；Redis 客户端遵循 limits 的兼容范围，服务端与客户端不要混为同一版本
- SQLAlchemy 升至 2.1、SQLAlchemy-Utils 升至 0.43，保留 alembic-dddl 0.1.3；旧初始 migration 的 import/历史 SQL 仍需要兼容依赖，不因“未使用 import”删除它
- 时间助手改 zoneinfo，Windows 显式 tzdata；不再依赖间接安装的 pytz

依赖替换与调用方必须一起合并；不能先移除库，再让业务在后续发布中慢慢改导入。

## 3. 配置与资源

旧的 `from config.xxx import settings`、全局 engine/redis_client/httpx_client 导入需要迁移到 `config.settings.Settings` 和应用依赖。Settings 在边界构造，服务函数显式接收 session、Redis、发送器等所需资源，不接收整个 app。

应用入口仍可为 `api_app:app` / `python main.py`，工厂为：

```python
create_app(settings=None, *, sms_sender_factory=None)
```

配置在 `app.state.settings`，运行资源在 `app.state.resources`。导入/工厂不创建运行客户端；每次 lifespan 创建并关闭自己的资源。不要在自己的代码中继续使用 close_all/close_all_sessions，也不要在并发任务间共享 AsyncSession。

| 变化 | 升级动作 |
| --- | --- |
| `APP_ENV` | 明确 development/test/production；生产拒绝 DEBUG 与演示凭据 |
| `JWT_SECRET_KEY` | 生成至少32字节的独立随机密钥，没有有效默认值 |
| `JWT_TTL` | 默认由旧长周期改为30分钟，客户端不能硬编码旧期限 |
| `JWT_ISSUER` / `JWT_AUDIENCE` | 明确新应用的签发与验证身份，切换时与 token 失效策略一起实施 |
| `APP_QPS` | 从按实际路径分桶变为每 IP 跨业务路径总配额；回环不豁免 |
| 可信代理 | 默认不信任何转发头，按真实网关配置 `APP_TRUSTED_PROXY_IPS` |
| CORS | `APP_SERVER_DOMAIN` 已移除；设置 JSON origins 列表，凭据单独开启 |
| Redis key | 增加本应用/环境独有的 namespace，同应用 worker 使用相同前缀 |
| DB pool | 默认4+4、pre-ping，按 worker 数计算总连接容量 |
| 日志 | stdout 默认，文件显式设置LOG_PATH；同进程共享日志配置，不按app随意重置handlers |
| SMS | 默认关闭；启用前设置独立密钥并注入 sender factory |

根 `.env` 是唯一 dotenv 来源，进程环境优先。不要再复制 docker/.env。单元测试需要同时隔离进程环境，`Settings(_env_file=None)` 本身并不会清除父进程变量。

## 4. 数据库 schema 与回退

保留 `883992f5b42f` 及其 revisioned SQL，追加迁移，不重建初始 revision。旧项目若已有自己的字段或迁移分支，应由它自己的新 revision 显式合并，而不是套用模板 revision 覆盖业务 schema。

本轮 schema 主要变化：

- cellphone 改为可空，以支持不绑定手机号的用户名注册；password 原本已可空，继续支持手机号账号
- UUID 数据库默认改为 PostgreSQL 内建 gen_random_uuid()，不删除历史 uuid-ossp 扩展
- 保留时间列 NOT NULL、TIMESTAMPTZ 与数据库 BEFORE UPDATE trigger
- 核对并处理初始模板中的冗余 unique(id)，不删除旧项目未知的依赖约束
- username/cellphone 仍然全历史唯一，不改成“删除后可复用”的部分唯一索引

所有 Alembic 命令使用 `uv run --locked python -X utf8 -m alembic ...`。URL 构造支持特殊字符，但不要在日志中输出完整连接串。

DDDL 插件检查的是当前 SQL 与最新历史 SQL，不读取数据库实际定义。必须另验 PostgreSQL catalog 中的 function/trigger/view，以及 enum、ICU collation、默认值和实际更新行为。移除 DDL 登记不会自动生成 DROP，必须显式写入迁移生成源。

### 条件性降级

`head → 883992f5b42f` 不是对任意数据都无损可行：旧版本要求 cellphone NOT NULL。

- 无 NULL cellphone：在停止写入的副本验证降级、再升级，确认默认值/约束还原
- 已有 NULL cellphone：downgrade 会在反向 DDL 前明确拒绝，revision、schema 和数据保持不变；先由业务方处理这些账号
- 不允许删除账号、填随机手机号或假装降级已通过；降级预检与 DDL 之间必须停止业务写入
- 数据库回退不等于应用回退安全，Argon2 兼容也必须先确认

PostgreSQL **15→18** 的引擎大版本升级使用支持的 dump/restore 或 pg_upgrade 流程另排，不能与 schema 升级无说明地捆绑上线，也不能把旧15数据目录直接挂给18镜像。

## 5. 必须实际失效旧 token

**不能只通知客户端重新登录。** 吊销 key 从原始 token 改为摘要后，若仍用同一个密钥和验证身份接受旧 token，旧格式黑名单里的已吊销凭据可能重新有效。

本轮选择不迁移旧 token 黑名单，因此发布时必须轮换签名密钥或验证 issuer/audience，确保旧 token 全部实际被拒绝，包括旧的正常 token 和已吊销 token。

新 token 默认30分钟，不会使已签发的旧7天 token 自动缩短。不要用新 TTL 推断旧凭据已经过期。若旧项目坚持继续接受旧 token，应另行设计旧吊销状态兼容，不能直接使用模板默认切换方案。

退出仍可吊销有效凭据，不因账号禁用而剥夺退出能力；不新增重复退出幂等契约。token status 和受保护接口则必须确认账号仍存在、启用且未删除。

## 6. 密码兼容与事务

保留已有 bcrypt 哈希；密码验证成功且账号可用时升级为 Argon2，并在返回成功 token 前确认事务提交。

- 12–128字符是新设置密码规则，不阻止旧短密码登录升级
- 密码不 trim/规范化/截断；bcrypt 的上限按 UTF-8 字节计算，超过72字节拒绝匹配，需要旧项目自行安排重设
- 升级提交失败不返回成功 token；不自动重试整个认证/验证码流程
- 账号创建已提交，但签名/响应随后失败时，不能承诺数据库未变化；连接故障下提交结果也可能未知
- 一旦新代码写入 Argon2，旧应用若不支持读取就不能盲目回滚旧镜像

模板不新增密码找回、刷新 token 或会话管理系统，不能把这些升级限制当作相关功能已经存在。

## 7. 手机号流程

公开注册 password 改为必填；nickname/gender 仍必填。cellphone 与 cellphone_verification_code 成对可选，不再把验证字段展开进 ORM。内部手机号建号不使用公开注册 DTO 的空值绕过规则，而是显式创建普通、无密码账号。

发送请求现在必须有 purpose：

```json
{"cellphone":"13800000000","purpose":"login"}
```

register/login challenge 隔离，旧未消费验证码与旧万能码不迁移。先完成供应商接入，再启用短信；发送器通过 factory 每次 lifespan 重建，实例由该周期关闭。

发送仅承诺供应商接受，不承诺最终送达。失败、超时、确认未知时不自动重发；503 后用户仍可能收到短信。验证码消费后 DB 失败不恢复旧码，需要重新发送，不能通过重试整个流程制造重复发信。

禁用/已删除手机号占用历史唯一身份：公开注册409，验证码登录401，不自动复活、换绑或创建第二个账号。未来生效的删除时间仍按“尚未删除”语义处理。

## 8. 客户端与部署兼容变化

- 注册成功201，重复身份409；错误身份/禁用/删除账号统一401，权限不足403
- 输入/手机验证码错误422，限流429（标准Retry-After），短信与依赖不可用503
- 错误统一 `{code,message,detail?}`，422不再返回原始输入/旧detail形状；成功响应不套envelope
- `/users/me` 是最小受保护接口，仅本人公开字段；注册额外内部属性不能生效
- WS 不再从 query 读取 access_token，只提供非浏览器 Authorization 头契约；浏览器认证由下游单独设计
- 默认不信代理，生产必须验证真实 Uvicorn 入口下的 client/proto，不以手动改 ASGI scope 的单元测试代替
- ping/live 不依赖 Redis；ready 的503使用状态模型，不与业务错误envelope混淆；探针访问由部署网络约束
- 生产脚本不再自动迁移或安装依赖；发布阶段先同步lock和迁移，再exec启动Web/独立scheduler
- scheduler默认单实例，只保证协作异步作业的正常等待/取消，不保证阻塞线程硬退出或分布式exactly-once

移除的非核心扩展：`httpx_helper` 并行下载器、`mimetypes_provider`、`get_bytes_mime_type`、`csrf_helper` 及其专属依赖/异常/配置。旧业务确实依赖时，留在自身业务代码中另行维护，不从模板升级结果中假定它们仍存在。

保留普通HTTPX客户端、随机字符串、Base64形态判断、时间/路径小型助手。时间助手不再猜naive datetime的本地时区；路径助手明确拒绝绝对路径、盘符、父目录和符号链接逃逸，不反复URL解码，也不承诺后续文件打开免TOCTOU。调用方须对照新契约迁移。

## 9. 发布前演练

在独立副本验证安装和核心组合流程：旧基线上迁移、用户名/手机号认证闭环、旧bcrypt升级、吊销、并发唯一冲突、Redis故障、可信代理和进程退出。测试以公开流程稳定为目标，不逐 helper/参数穷举，也不为 mock 拆分生产代码；下游新增 WS 等业务时，再补对应的核心流程测试。

分别记录静态/单元、真实PG/Redis、迁移、进程/代理及平台结果。缺服务跳过测试不能写成已通过。实际生产变更仍需旧项目自己的评审、备份和发布安排。
