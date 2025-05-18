# FastAPI Starter Kit

## 项目概述

FastAPI Starter Kit 是一个基于 FastAPI 框架的高性能、可扩展的 Web 应用脚手架，旨在为开发者提供一个结构清晰、功能完备的起点，快速构建现代化的 API 服务。该脚手架集成了用户认证、数据库管理、任务调度、日志记录等常见功能，并遵循模块化设计原则，方便二次开发和维护。

本项目适用于构建 RESTful API、微服务架构或需要高并发支持的应用程序，特别适合对性能和开发效率有较高要求的场景。无论是初学者还是资深开发者，都可以通过此脚手架快速上手并定制符合业务需求的应用。

## 核心特性

- **高性能框架**：基于 FastAPI，充分利用异步编程，提供极高的请求处理速度。
- **模块化架构**：代码结构清晰，分为核心业务逻辑、配置、启动模块等，易于扩展和维护。
- **用户认证与授权**：内置完整的认证系统，支持 JWT、OAuth2 等多种认证方式。
- **数据库支持**：集成 SQLModel（基于 SQLAlchemy），提供简洁的 ORM 体验，当前使用 PostgreSQL 作为主要数据库，并可通过配置扩展至其他数据库。
- **缓存与存储**：内置 Redis 支持，用于高效缓存和会话管理，提升应用性能。
- **任务调度**：内置异步任务调度器（APScheduler），支持定时任务和后台任务处理。
- **日志与监控**：完善的日志系统，便于调试和生产环境监控。
- **生产就绪**：提供开发和生产环境配置。

## 项目结构

以下是项目的目录结构概览，每个目录和关键文件都附带了功能说明，以便开发者快速了解代码组织方式：

```txt
fastapi-starter
├── main.py                 # 项目主入口文件，通过uvicorn启动FastAPI应用
├── api_app.py              # API应用主文件，定义并创建FastAPI应用实例
├── scheduler.py            # 调度器主文件，处理定时任务
├── app                     # 核心应用目录，包含主要业务逻辑
│   ├── http                # HTTP相关模块，包含API端点和中间件
│   │   ├── api             # API路由定义目录，包含具体的接口实现
│   │   ├── deps            # 依赖注入目录，处理路由依赖逻辑
│   │   └── middleware      # 中间件目录，处理请求和响应的中间逻辑
│   ├── models              # 数据库模型目录，定义ORM模型
│   ├── schemas             # 数据模式目录，定义请求和响应的数据结构
│   ├── services            # 服务层目录，处理业务逻辑
│   ├── providers           # 服务提供者目录，包含应用初始化和依赖提供逻辑
│   ├── exceptions          # 异常处理模块，定义项目中的自定义异常
│   ├── support             # 辅助工具目录，包含通用工具函数
│   └── jobs                # 任务调度目录，包含定时任务或后台任务
├── bootstrap               # 应用启动目录，包含初始化逻辑
│   ├── application.py      # 应用启动主文件，初始化FastAPI应用并注册核心提供者
│   └── scheduler.py        # 异步任务调度器初始化文件，配置和管理定时任务
├── config                  # 配置目录，存储项目配置信息
├── database                # 数据库相关目录，包含SQL脚本等
│   └── postgresql          # PostgreSQL数据库相关脚本目录
├── start_fastapi.sh        # 启动FastAPI应用的脚本（生产模式时使用）
├── start_scheduler.sh      # 启动调度器的脚本（生产模式时使用）
├── migrations              # 数据库迁移目录，存储Alembic迁移脚本
└── storage                 # 存储目录，用于保存日志或临时文件
    └── logs                # 日志存储目录
```

## 快速开始

### 环境准备

1. **安装数据库**：安装 PostgreSQL 15 和 Redis 6（Docker 下可使用 `postgres:15-alpine` 和 `redis:6-alpine` 镜像）。
2. **安装依赖**：确保已安装 Python 3.8+，然后使用 `pip install -r requirements.txt` 安装项目依赖。
3. **配置环境变量**：项目提供 `.env.example` 作为模板，可拷贝为 `.env` 并修改环境变量（如 PostgreSQL、Redis 连接、认证密钥等），与 `config` 目录对应，后续可扩展更多变量。
4. **数据库初始化**：PostgreSQL 中创建好相应数据库后，运行 `alembic upgrade head` 应用数据库迁移，初始化数据库表结构。

### 运行项目

- **开发模式**：运行 `python main.py` 启动 FastAPI 应用，带有自动重载的开发服务器；如需任务调度，需额外运行 `python scheduler.py` 启动调度器。
- **生产模式**：使用提供的脚本 `./start_fastapi.sh` 启动 FastAPI 应用，或 `./start_scheduler.sh` 启动任务调度器。

## 贡献与反馈

欢迎对本项目提出改进建议或提交代码贡献！如果在使用过程中遇到问题，请通过 GitHub Issues 提交反馈，我们会尽快响应。你也可以通过 Fork 本仓库并提交 Pull Request 来参与开发。

## 许可证

本项目采用 MIT 许可证，详情请参见 LICENSE 文件。你可以自由使用、修改和分发本代码，但请保留原作者信息。