# AI Service 微服务架构实施计划

## 概述

本文档详细描述了将 Immich AI Service 从单体架构改造为基于 Envoy 网关的微服务架构的完整实施计划。该计划按照优先级分阶段实施，确保系统平稳演进。

## 1. 目标与收益

### 1.1 核心目标
1. **服务解耦**：将 OCR、人脸识别、视频分析拆分为独立微服务
2. **网关统一**：使用 Envoy 作为统一 API 网关，避免重复造轮子
3. **独立部署**：各服务可独立运行、扩展和升级
4. **生产就绪**：增强监控、安全、持久化等生产级特性

### 1.2 预期收益
- **可扩展性**：按需扩展特定服务，资源利用率提升
- **可靠性**：故障隔离，单个服务问题不影响整体
- **维护性**：独立代码库，团队可并行开发
- **技术异构**：不同服务可采用最适合的技术栈

## 2. 架构设计

### 2.1 目标架构图

```
┌─────────────────────────────────────────────────────────┐
│                    Client Requests                       │
│                    (HTTP/HTTPS)                          │
└──────────────────────────┬──────────────────────────────┘
                           │
                ┌──────────▼──────────┐
                │    Envoy Gateway     │
                │   (Port: 8080)       │
                │   • 动态路由         │
                │   • 负载均衡         │
                │   • TLS终止         │
                │   • API Key验证     │
                │   • 速率限制        │
                └──────────┬──────────┘
                           │
    ┌──────────────────────┼──────────────────────┐
    │                      │                      │
┌───▼─────┐        ┌──────▼──────┐        ┌─────▼──────┐
│ OCR     │        │ Face        │        │ Video      │
│ Service │        │ Service     │        │ Service    │
│ :8001   │        │ :8002       │        │ :8003      │
│         │        │             │        │            │
│ • Rapid │        │ • Insight   │        │ • OpenCV   │
│   OCR   │        │   Face      │        │ • 异步任务 │
│ • 文本  │        │ • FAISS     │        │ • Redis    │
│   识别  │        │ • 持久化    │        │   队列     │
└─────────┘        └─────────────┘        └────────────┘
    │                     │                      │
    └─────────────────────┼──────────────────────┘
                          │
                  ┌───────▼───────┐
                  │ Shared        │
                  │ Storage       │
                  │               │
                  │ • FAISS索引   │
                  │ • SQLite      │
                  │ • Redis       │
                  └───────────────┘
```

### 2.2 技术栈选择

| 组件 | 技术选择 | 理由 |
|------|----------|------|
| API 网关 | Envoy v1.24+ | 高性能、可扩展、云原生标准 |
| 服务框架 | FastAPI | 异步支持、自动文档、类型提示 |
| 向量搜索 | FAISS | 高性能相似度搜索 |
| 数据存储 | SQLite + FAISS文件 | 轻量级、无需额外服务 |
| 任务队列 | Redis + RQ/Celery | 成熟异步处理方案 |
| 容器编排 | Docker Compose | 开发环境简化 |
| 监控 | Prometheus + Grafana | 标准监控方案 |

## 3. 任务拆解（按优先级分组）

### 3.1 第一阶段：基础架构改造（高优先级）

#### 任务 1.1：Envoy 网关搭建
**目标**：配置 Envoy 作为统一的 API 网关
**交付物**：
- `envoy.yaml` 配置文件
- API Key 验证 Lua 过滤器
- 路由规则配置
- 健康检查端点

**详细任务**：
1. Envoy 容器化配置（Dockerfile）
2. 静态路由配置（初期）
3. API Key 验证实现
4. 请求日志和指标收集
5. 与现有服务集成测试

**技术要点**：
```yaml
# 路由配置示例
routes:
- match: { prefix: "/v1/ocr" }
  route: { cluster: "ocr_service" }
- match: { prefix: "/v1/face" }
  route: { cluster: "face_service" }
- match: { prefix: "/v1/video" }
  route: { cluster: "video_service" }
```

#### 任务 1.2：服务拆分
**目标**：将单体服务拆分为三个独立微服务

| 服务 | 端口 | 职责 | 独立运行命令 |
|------|------|------|--------------|
| OCR Service | 8001 | 文字识别 | `uvicorn app.main:app --port 8001` |
| Face Service | 8002 | 人脸识别 | `uvicorn app.main:app --port 8002` |
| Video Service | 8003 | 视频分析 | `uvicorn app.main:app --port 8003` |

**详细任务**：
1. 创建独立项目结构
   ```
   ai-service-micro/
   ├── envoy/           # Envoy 配置
   ├── ocr-service/     # OCR 微服务
   ├── face-service/    # 人脸识别微服务
   ├── video-service/   # 视频分析微服务
   └── shared/          # 共享工具库
   ```

2. 代码迁移策略
   - 提取共享工具函数
   - 保持 API 接口兼容性
   - 逐步迁移，分步验证

3. 服务间通信
   - Video Service 通过 HTTP 调用 Face Service
   - 超时和重试配置
   - 错误处理机制

#### 任务 1.3：数据持久化
**目标**：解决人脸数据重启丢失问题

**详细任务**：
1. FAISS 索引文件存储
   ```python
   # 保存索引
   faiss.write_index(index, "/data/faces.index")

   # 加载索引
   index = faiss.read_index("/data/faces.index")
   ```

2. SQLite 元数据存储
   ```sql
   CREATE TABLE faces (
       id INTEGER PRIMARY KEY,
       name TEXT NOT NULL,
       created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
       embedding_id INTEGER
   );
   ```

3. 数据迁移脚本
   ```bash
   python scripts/migrate_faces.py --source memory --target file
   ```

#### 任务 1.4：配置管理
**目标**：实现配置外部化和环境化管理

**详细任务**：
1. 统一配置模块设计
2. 环境变量支持
3. 配置文件验证
4. 热重载支持（可选）

### 3.2 第二阶段：核心功能增强（中优先级）

#### 任务 2.1：错误处理完善
**目标**：统一错误处理，提升用户体验

**详细任务**：
1. 全局异常处理中间件
2. 多人脸识别支持
3. 置信度阈值配置
4. 详细的错误消息和文档链接

#### 任务 2.2：监控和可观测性
**目标**：实现生产级监控

**详细任务**：
1. Prometheus 指标收集
   - HTTP 请求统计
   - 处理延迟直方图
   - 内存使用监控

2. 结构化日志
   ```python
   import structlog
   logger = structlog.get_logger()
   logger.info("face_registered", name=name, embedding_size=len(embedding))
   ```

3. 健康检查端点
   ```python
   @app.get("/health")
   def health_check():
       return {
           "status": "healthy",
           "services": {
               "database": check_database(),
               "models": check_models()
           }
       }
   ```

#### 任务 2.3：安全性增强
**目标**：加强 API 安全防护

**详细任务**：
1. 多 API Key 管理
2. 请求频率限制
3. 文件上传验证
4. CORS 配置优化

#### 任务 2.4：性能优化
**目标**：提升服务响应速度和吞吐量

**详细任务**：
1. 模型量化（INT8）
2. 批处理 API 支持
3. 响应缓存实现
4. 内存使用限制

### 3.3 第三阶段：高级特性（低优先级）

#### 任务 3.1：微服务治理
**目标**：完善微服务生态系统

**详细任务**：
1. 服务注册与发现
2. 分布式链路追踪
3. 熔断和降级机制
4. 配置中心集成

#### 任务 3.2：高级功能扩展
**目标**：扩展 AI 能力边界

**详细任务**：
1. 物体检测集成
2. 场景识别
3. 音频分析
4. 多语言 OCR 增强

#### 任务 3.3：部署优化
**目标**：实现生产级部署能力

**详细任务**：
1. Kubernetes Helm Chart
2. 自动扩缩容配置
3. 蓝绿部署策略
4. 多区域部署支持

## 4. 详细实施计划

### 第 1 周：Envoy 网关搭建

#### Day 1-2：Envoy 基础配置
**目标**：完成 Envoy 基本路由配置
**任务**：
- [ ] 安装 Envoy 开发环境
- [ ] 编写基本路由配置（`envoy.yaml`）
- [ ] 配置静态服务发现
- [ ] 测试 HTTP 代理功能

**验收标准**：
- Envoy 能够代理请求到现有单体服务
- 路由规则正确匹配
- 日志输出正常

#### Day 3-4：安全功能实现
**目标**：实现 API 安全特性
**任务**：
- [ ] API Key 验证 Lua 过滤器
- [ ] 请求速率限制配置
- [ ] TLS/SSL 配置（可选，开发环境可跳过）
- [ ] CORS 配置

**验收标准**：
- 无效 API Key 返回 401
- 超频请求返回 429
- CORS 头部正确设置

#### Day 5：集成测试
**目标**：网关与现有服务集成测试
**任务**：
- [ ] 端到端 API 测试
- [ ] 性能基准测试
- [ ] 压力测试（可选）
- [ ] 更新部署文档

**验收标准**：
- 所有 API 通过网关正常访问
- 性能衰减 < 10%
- 文档包含网关配置说明

### 第 2 周：服务拆分

#### Day 1-2：OCR 服务独立
**目标**：拆分 OCR 服务为独立微服务
**任务**：
- [ ] 创建 `ocr-service/` 目录结构
- [ ] 迁移 OCR 相关代码
- [ ] 编写独立 Dockerfile
- [ ] 配置服务依赖（模型文件）

**目录结构**：
```
ocr-service/
├── app/
│   ├── main.py
│   └── ocr.py
├── requirements.txt
├── Dockerfile
└── config.yaml
```

#### Day 3-4：人脸识别服务独立
**目标**：拆分人脸识别服务
**任务**：
- [ ] 创建 `face-service/` 目录
- [ ] 迁移人脸识别代码
- [ ] 实现持久化存储
- [ ] 配置模型文件路径

**技术要点**：
- FAISS 索引文件持久化
- SQLite 数据库存储元数据
- 数据迁移脚本

#### Day 5：视频分析服务独立
**目标**：拆分视频分析服务
**任务**：
- [ ] 创建 `video-service/` 目录
- [ ] 迁移视频分析代码
- [ ] 集成 Redis 任务队列
- [ ] 实现服务间通信（调用 Face Service）

### 第 3 周：数据持久化与配置

#### Day 1-2：FAISS 持久化实现
**目标**：完成人脸数据持久化
**任务**：
- [ ] 实现索引文件存储
- [ ] 添加数据备份机制
- [ ] 编写数据迁移脚本
- [ ] 测试数据恢复功能

#### Day 3-4：配置管理系统
**目标**：统一配置管理
**任务**：
- [ ] 创建共享配置模块
- [ ] 支持环境变量覆盖
- [ ] 添加配置验证
- [ ] 编写配置文档

#### Day 5：集成测试
**目标**：验证拆分后的系统
**任务**：
- [ ] 端到端功能测试
- [ ] 数据持久化验证
- [ ] 性能回归测试
- [ ] 部署验证

### 第 4 周：监控与安全

#### Day 1-2：监控系统实现
**目标**：添加监控和可观测性
**任务**：
- [ ] Prometheus 指标收集
- [ ] 健康检查端点
- [ ] Grafana 仪表板配置
- [ ] 告警规则设置

#### Day 3-4：安全增强
**目标**：加强安全防护
**任务**：
- [ ] API Key 管理数据库
- [ ] 请求频率限制实现
- [ ] 文件上传验证加固
- [ ] 安全扫描集成

#### Day 5：文档和部署
**目标**：完成部署准备
**任务**：
- [ ] 更新部署文档
- [ ] 创建生产环境 Docker Compose
- [ ] 性能优化验证
- [ ] 创建迁移指南

## 5. 各服务独立运行指南

### 5.1 OCR 服务独立运行

```bash
# 1. 进入服务目录
cd ocr-service

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动服务
uvicorn app.main:app --host 0.0.0.0 --port 8001

# 4. 测试 API
curl -X POST http://localhost:8001/v1/ocr/scan \
  -H "x-api-key: your-key" \
  -F "file=@test.png"
```

**配置项**：
```yaml
# config.yaml
app:
  port: 8001
  api_key: ${API_KEY}

models:
  ocr:
    provider: rapidocr
    model_path: ./models/rapidocr
```

### 5.2 人脸识别服务独立运行

```bash
# 1. 进入服务目录
cd face-service

# 2. 初始化数据库
python scripts/init_db.py

# 3. 启动服务
uvicorn app.main:app --host 0.0.0.0 --port 8002

# 4. 注册人脸
curl -X POST http://localhost:8002/v1/face/register \
  -H "x-api-key: your-key" \
  -F "name=张三" \
  -F "file=@face.jpg"
```

**数据持久化**：
- 索引文件：`./data/faces.index`
- 数据库：`./data/faces.db`
- 备份目录：`./backups/`

### 5.3 视频分析服务独立运行

```bash
# 1. 启动 Redis（任务队列）
docker run -d -p 6379:6379 redis:alpine

# 2. 进入服务目录
cd video-service

# 3. 启动服务
uvicorn app.main:app --host 0.0.0.0 --port 8003

# 4. 提交视频分析
curl -X POST http://localhost:8003/v1/video/analyze \
  -H "x-api-key: your-key" \
  -F "file=@video.mp4"
```

**服务依赖**：
- Redis: 任务队列（端口 6379）
- Face Service: 人脸识别（通过 HTTP 调用）

### 5.4 Envoy 网关独立运行

```bash
# 1. 进入网关目录
cd envoy

# 2. 启动 Envoy
docker run -d \
  -p 8080:8080 \
  -v $(pwd)/envoy.yaml:/etc/envoy/envoy.yaml \
  envoyproxy/envoy:v1.24-latest

# 3. 通过网关访问
curl -X POST http://localhost:8080/v1/ocr/scan \
  -H "x-api-key: your-key" \
  -F "file=@test.png"
```

## 6. Envoy 详细配置

### 6.1 完整配置文件示例

```yaml
# envoy/envoy.yaml
admin:
  address:
    socket_address:
      address: 0.0.0.0
      port_value: 9901

static_resources:
  listeners:
  - name: main_listener
    address:
      socket_address:
        address: 0.0.0.0
        port_value: 8080
    filter_chains:
    - filters:
      - name: envoy.filters.network.http_connection_manager
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager
          stat_prefix: ingress_http
          codec_type: AUTO
          route_config:
            name: local_route
            virtual_hosts:
            - name: ai_service
              domains: ["*"]
              routes:
              - match:
                  prefix: "/v1/ocr"
                route:
                  cluster: ocr_service
                  prefix_rewrite: "/v1/ocr"
              - match:
                  prefix: "/v1/face"
                route:
                  cluster: face_service
                  prefix_rewrite: "/v1/face"
              - match:
                  prefix: "/v1/video"
                route:
                  cluster: video_service
                  prefix_rewrite: "/v1/video"
              - match:
                  prefix: "/health"
                route:
                  cluster: admin_service
          http_filters:
          - name: envoy.filters.http.lua
            typed_config:
              "@type": type.googleapis.com/envoy.extensions.filters.http.lua.v3.Lua
              inline_code: |
                function envoy_on_request(request_handle)
                  -- API Key 验证
                  local api_key = request_handle:headers():get("x-api-key")
                  local valid_keys = {
                    ["your-secret-api-key"] = true,
                    ["another-key"] = true
                  }

                  if not api_key or not valid_keys[api_key] then
                    request_handle:respond(
                      {[":status"] = "401"},
                      "{\"error\": \"Invalid or missing API Key\"}"
                    )
                  end

                  -- 添加请求 ID
                  local request_id = tostring(math.random(1000000, 9999999))
                  request_handle:headers():add("x-request-id", request_id)
                end
          - name: envoy.filters.http.router
            typed_config:
              "@type": type.googleapis.com/envoy.extensions.filters.http.router.v3.Router

  clusters:
  - name: ocr_service
    connect_timeout: 5s
    type: STRICT_DNS
    lb_policy: ROUND_ROBIN
    load_assignment:
      cluster_name: ocr_service
      endpoints:
      - lb_endpoints:
        - endpoint:
            address:
              socket_address:
                address: ocr-service
                port_value: 8001
    health_checks:
    - timeout: 1s
      interval: 10s
      unhealthy_threshold: 3
      healthy_threshold: 1
      http_health_check:
        path: "/health"

  - name: face_service
    connect_timeout: 5s
    type: STRICT_DNS
    lb_policy: ROUND_ROBIN
    load_assignment:
      cluster_name: face_service
      endpoints:
      - lb_endpoints:
        - endpoint:
            address:
              socket_address:
                address: face-service
                port_value: 8002

  - name: video_service
    connect_timeout: 10s  # 视频处理需要更长时间
    type: STRICT_DNS
    lb_policy: ROUND_ROBIN
    load_assignment:
      cluster_name: video_service
      endpoints:
      - lb_endpoints:
        - endpoint:
            address:
              socket_address:
                address: video-service
                port_value: 8003

  - name: admin_service
    connect_timeout: 1s
    type: STATIC
    load_assignment:
      cluster_name: admin_service
      endpoints:
      - lb_endpoints:
        - endpoint:
            address:
              socket_address:
                address: 0.0.0.0
                port_value: 9901
```

### 6.2 配置说明

#### 路由策略
- **前缀匹配**：根据 URL 前缀路由到对应服务
- **路径重写**：保持 API 路径一致性
- **健康检查**：自动剔除不健康实例

#### 安全特性
- **API Key 验证**：Lua 过滤器实现
- **请求 ID**：便于追踪和日志关联
- **超时配置**：防止请求长时间阻塞

#### 监控配置
- **管理接口**：端口 9901，用于状态查询
- **访问日志**：可配置输出格式
- **统计信息**：Prometheus 格式指标

## 7. Docker Compose 配置

### 7.1 开发环境配置

```yaml
# docker-compose.dev.yaml
version: '3.8'

services:
  envoy:
    image: envoyproxy/envoy:v1.24-latest
    ports:
      - "8080:8080"
      - "9901:9901"
    volumes:
      - ./envoy/envoy.yaml:/etc/envoy/envoy.yaml
    depends_on:
      - ocr-service
      - face-service
      - video-service

  ocr-service:
    build: ./ocr-service
    ports:
      - "8001:8001"
    environment:
      - API_KEY=your-secret-api-key
    volumes:
      - ./ocr-service/models:/app/models

  face-service:
    build: ./face-service
    ports:
      - "8002:8002"
    environment:
      - API_KEY=your-secret-api-key
      - DATABASE_URL=sqlite:///data/faces.db
    volumes:
      - ./face-service/data:/app/data
      - ./face-service/models:/app/models

  video-service:
    build: ./video-service
    ports:
      - "8003:8003"
    environment:
      - API_KEY=your-secret-api-key
      - REDIS_URL=redis://redis:6379
      - FACE_SERVICE_URL=http://face-service:8002
    depends_on:
      - redis
      - face-service

  redis:
    image: redis:alpine
    ports:
      - "6379:6379"

  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    volumes:
      - ./monitoring/grafana/provisioning:/etc/grafana/provisioning
```

### 7.2 生产环境建议

1. **网络配置**
   - 使用自定义网络
   - 限制服务间通信
   - 配置 TLS 加密

2. **资源限制**
   ```yaml
   deploy:
     resources:
       limits:
         memory: 1G
         cpus: '0.5'
   ```

3. **健康检查**
   ```yaml
   healthcheck:
     test: ["CMD", "curl", "-f", "http://localhost:8001/health"]
     interval: 30s
     timeout: 10s
     retries: 3
   ```

## 8. 风险评估与缓解

### 8.1 技术风险

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| API 不兼容 | 高 | 中 | 版本化 API，提供迁移期 |
| 数据丢失 | 高 | 低 | 定期备份，数据验证 |
| 性能下降 | 中 | 中 | 性能基准测试，逐步优化 |
| 部署复杂 | 中 | 高 | 自动化部署脚本，详细文档 |

### 8.2 业务风险

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| 服务中断 | 高 | 低 | 蓝绿部署，回滚机制 |
| 数据不一致 | 中 | 中 | 数据同步机制，一致性检查 |
| 安全漏洞 | 高 | 低 | 安全扫描，定期审计 |

### 8.3 组织风险

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| 团队技能不足 | 中 | 中 | 培训，外部专家支持 |
| 进度延误 | 中 | 高 | 分阶段实施，定期评审 |
| 沟通成本增加 | 中 | 高 | 明确接口规范，API 文档 |

## 9. 成功标准与验收指标

### 9.1 技术指标
- [ ] 网关延迟增加 < 10ms
- [ ] 服务拆分后功能完整度 100%
- [ ] 数据持久化成功率 99.9%
- [ ] 监控覆盖率 90% 以上

### 9.2 业务指标
- [ ] API 兼容性保持 100%
- [ ] 服务可用性 99.5% 以上
- [ ] 平均响应时间 < 500ms（P95）
- [ ] 错误率 < 0.1%

### 9.3 运维指标
- [ ] 部署时间 < 10 分钟
- [ ] 回滚时间 < 5 分钟
- [ ] 监控告警覆盖率 100%
- [ ] 文档完整度 100%

## 10. 下一步行动

### 短期行动（1-2周）
1. [ ] 成立项目小组，明确角色职责
2. [ ] 搭建开发环境，准备代码仓库
3. [ ] 完成 Envoy 网关原型验证
4. [ ] 制定详细的 API 接口规范

### 中期行动（3-4周）
1. [ ] 完成服务拆分和独立部署
2. [ ] 实现数据持久化方案
3. [ ] 建立监控和告警系统
4. [ ] 完成第一轮集成测试

### 长期行动（1-2月）
1. [ ] 生产环境部署验证
2. [ ] 性能优化和安全加固
3. [ ] 自动化运维工具链
4. [ ] 团队培训和知识转移

## 附录

### A. 相关文档链接
- [AI Service 用户手册](./ai-service-user-manual.md)
- [AI Service 优化建议](./ai-service-optimization.md)
- [AI Service 重构方案](./ai-service-refactoring.md)

### B. 工具和资源
- **Envoy 文档**: https://www.envoyproxy.io/docs
- **FastAPI 文档**: https://fastapi.tiangolo.com
- **FAISS 文档**: https://github.com/facebookresearch/faiss
- **Prometheus 文档**: https://prometheus.io/docs

### C. 联系人信息
- **架构设计**: [联系人]
- **开发实施**: [联系人]
- **运维支持**: [联系人]
- **项目管理**: [联系人]

---

**文档版本**: 1.0
**最后更新**: 2026-03-02
**维护团队**: AI Service 开发团队
**状态**: 草案（待评审）