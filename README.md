# FastAPI Starter Kit

## 项目概述

FastAPI Starter Kit 是一个基于 FastAPI 框架的高性能、可扩展的 Web 应用脚手架，旨在为开发者提供一个结构清晰、功能完备的起点，快速构建现代化的 API 服务。该脚手架集成了用户认证、数据库管理、任务调度、日志记录等常见功能，并遵循模块化设计原则，方便二次开发和维护。

本项目适用于构建 RESTful API、微服务架构或需要高并发支持的应用程序，特别适合对性能和开发效率有较高要求的场景。无论是初学者还是资深开发者，都可以通过此脚手架快速上手并定制符合业务需求的应用。

## 系统要求

- **Python**：3.8+ 版本
- **操作系统**：
  - **Linux**：完全支持，已在生产环境验证 ✅
  - **Windows**：支持，提供专用依赖和编码处理 ✅
  - **macOS**：理论支持，建议使用 Linux 依赖配置 ⚠️
- **数据库**：PostgreSQL 15 / Redis 6（推荐使用 Docker）

## 核心特性

- **高性能框架**：基于 FastAPI，充分利用异步编程，提供极高的请求处理速度。
- **模块化架构**：代码结构清晰，分为核心业务逻辑、配置、启动模块等，易于扩展和维护。
- **用户认证与授权**：内置完整的认证系统，支持 JWT、OAuth2 等多种认证方式。
- **数据库支持**：集成 SQLAlchemy 2.0，提供简洁的 ORM 体验，当前使用 PostgreSQL 作为主要数据库，并可通过配置扩展至其他数据库。
- **缓存与存储**：内置 Redis 支持，用于高效缓存和会话管理，提升应用性能。
- **任务调度**：内置异步任务调度器（APScheduler），支持定时任务和后台任务处理。
- **日志与监控**：完善的日志系统，便于调试和生产环境监控。
- **跨平台支持**：经过 Linux 和 Windows 环境测试，理论上支持 macOS。
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
│   ├── support             # 辅助工具目录，包含通用工具函数
│   └── jobs                # 任务调度目录，包含定时任务或后台任务
│   ├── exceptions.py       # 异常处理模块，定义项目中的自定义异常
├── bootstrap               # 应用启动目录，包含初始化逻辑
│   ├── application.py      # 应用启动主文件，初始化FastAPI应用并注册核心提供者
│   └── scheduler.py        # 异步任务调度器初始化文件，配置和管理定时任务
├── config                  # 配置目录，存储项目配置信息
├── database                # 数据库相关目录，包含SQL脚本等
│   └── postgresql          # PostgreSQL数据库相关脚本目录
├── docker                  # Docker容器化配置目录，包含数据库服务编排文件
├── start_web.sh            # 启动Web应用的脚本（生产模式时使用）
├── start_scheduler.sh      # 启动调度器的脚本（生产模式时使用）
├── migrations              # 数据库迁移目录，存储Alembic迁移脚本
└── storage                 # 存储目录，用于保存日志或临时文件
    └── logs                # 日志存储目录
```

## 快速开始

### 环境准备

#### 1. Python 环境设置

确保已安装 Python 3.8+ 版本，然后创建并激活虚拟环境：

```bash
# 创建虚拟环境
python -m venv fastapi-env

# 激活虚拟环境
# Linux/macOS:
source fastapi-env/bin/activate
# Windows:
fastapi-env\Scripts\activate
```

#### 2. 安装项目依赖

根据你的操作系统选择对应的依赖文件：

```bash
# Linux/macOS 用户
pip install -r requirements.txt

# Windows 用户
pip install -r requirements-win.txt

# 开发环境（可选，包含开发工具）
pip install -r requirements-dev.txt
```

> **注意**：macOS 用户如遇到依赖问题，可尝试使用 `requirements-win.txt`

#### 3. 数据库服务启动

**方式一：使用 Docker（推荐）**

项目提供了 Docker Compose 配置文件，可以快速启动 PostgreSQL 和 Redis 服务：

```bash
# 启动数据库服务（PostgreSQL + Redis）
cd docker
docker-compose -f docker-compose-middleware.yaml up -d

# 查看服务状态
docker-compose -f docker-compose-middleware.yaml ps

# 停止服务（当需要时）
docker-compose -f docker-compose-middleware.yaml down
```

**方式二：手动安装**

如果不使用 Docker，需要手动安装：

- PostgreSQL 15（推荐使用 `postgres:15-alpine` 版本的配置）
- Redis 6（推荐使用 `redis:6-alpine` 版本的配置）

#### 4. 配置环境变量

复制环境变量模板并根据需要修改：

```bash
# 复制环境变量模板到项目根目录（供应用程序使用）
cp .env.example .env

# 如果使用 Docker 方式，还需要复制一份到 docker 目录（供 Docker Compose 使用）
cp .env.example docker/.env

# 编辑环境变量文件
# 开发环境：可以直接使用模板中的默认值
# 生产环境：必须修改密码和密钥等敏感信息，不能使用默认值
```

**注意**：如果你使用 Docker 方式启动数据库服务，需要确保 `docker/.env` 文件存在，否则 Docker Compose 将使用默认值。

#### 5. 数据库初始化

返回项目根目录，在 PostgreSQL 服务启动后，运行数据库迁移来初始化表结构：

```bash
# 确保在项目根目录下执行（如果之前在 docker 目录中，需要先返回上级目录）
cd ..

# 应用数据库迁移
alembic upgrade head
```

### 运行项目

- **开发模式**：运行 `python main.py` 启动 FastAPI 应用，带有自动重载的开发服务器；如需任务调度，需额外运行 `python scheduler.py` 启动调度器。
- **生产模式**：使用提供的脚本 `./start_fastapi.sh` 启动 FastAPI 应用，或 `./start_scheduler.sh` 启动任务调度器。

## 贡献与反馈

欢迎对本项目提出改进建议或提交代码贡献！如果在使用过程中遇到问题，请通过 GitHub Issues 提交反馈，我们会尽快响应。你也可以通过 Fork 本仓库并提交 Pull Request 来参与开发。

## 许可证

本项目采用 MIT 许可证，详情请参见 LICENSE 文件。你可以自由使用、修改和分发本代码，但请保留原作者信息。
