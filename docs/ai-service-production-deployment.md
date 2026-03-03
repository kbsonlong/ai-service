# AI 微服务系统生产部署指南

## 概述

本文档详细介绍了 AI 微服务系统在生产环境中的部署、配置和运维流程。系统基于微服务架构，包含三个核心 AI 服务（OCR、人脸识别、视频分析），通过 Envoy API 网关统一对外提供服务。

## 系统架构

```
┌─────────────────────────────────────────────────────────┐
│                    客户端请求                           │
│                   HTTP/HTTPS (8080)                     │
└──────────────────────────┬──────────────────────────────┘
                          │
               ┌──────────▼──────────┐
               │    Envoy 网关        │
               │   • 路由分发         │
               │   • API Key 验证     │
               │   • TLS 终止         │
               │   • 负载均衡         │
               └──────────┬──────────┘
                          │
    ┌─────────────────────┼─────────────────────┐
    │                     │                     │
┌───▼─────┐        ┌─────▼─────┐        ┌─────▼─────┐
│ OCR     │        │ 人脸识别   │        │ 视频分析   │
│ 服务     │        │ 服务       │        │ 服务       │
│ 8001    │        │ 8002      │        │ 8003      │
│         │        │           │        │           │
│ • 文字  │        │ • 人脸检测 │        │ • 视频处理 │
│   识别  │        │ • 人脸识别 │        │ • 异步任务 │
│ • 批量  │        │ • 批量处理 │        │ • Redis队列│
│   处理  │        │ • FAISS索引│        │           │
└─────────┘        └───────────┘        └───────────┘
    │                     │                     │
    └─────────────────────┼─────────────────────┘
                          │
                  ┌───────▼───────┐
                  │  共享组件      │
                  │               │
                  │ • Redis       │
                  │ • 监控        │
                  │ • 持久化存储  │
                  └───────────────┘
```

## 1. 先决条件

### 1.1 硬件要求

| 组件 | 最低配置 | 推荐配置 | 说明 |
|------|----------|----------|------|
| CPU | 4 核心 | 8 核心+ | 视频分析需要较强计算能力 |
| 内存 | 8 GB | 16 GB+ | AI 模型加载需要较大内存 |
| 存储 | 50 GB | 200 GB+ | 模型文件、持久化数据 |
| 网络 | 1 Gbps | 1 Gbps+ | 视频文件传输需要带宽 |

### 1.2 软件要求

- **操作系统**: Ubuntu 20.04+ / CentOS 8+ / RHEL 8+
- **容器运行时**: Docker 20.10+ 或 containerd
- **容器编排**: Docker Compose 1.29+（单机）或 Kubernetes 1.24+（集群）
- **数据库**: Redis 7.0+（任务队列）
- **监控**: Prometheus 2.40+，Grafana 9.0+

### 1.3 网络要求

- 开放端口：8080（API网关）、9090（Prometheus）、3000（Grafana）
- 内部服务通信：8001-8003、6379（Redis）
- 出站连接：用于下载模型文件（可选）

## 2. 快速部署（开发/测试环境）

### 2.1 使用 Docker Compose 部署

```bash
# 1. 克隆仓库
git clone <repository-url>
cd ai-service

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env 文件，设置 API_KEY 和其他参数

# 3. 启动所有服务
docker-compose -f docker-compose.microservices.yml up -d

# 4. 查看服务状态
docker-compose -f docker-compose.microservices.yml ps

# 5. 验证部署
curl http://localhost:8080/health
```

### 2.2 环境变量配置

创建 `.env` 文件：

```bash
# API 网关配置
API_KEY=your-production-api-key-here
ENVOY_LOG_LEVEL=info

# OCR 服务
OCR_API_KEY=${API_KEY}
OCR_PORT=8001
OCR_MODELS_DIR=/app/models
OCR_MAX_UPLOAD_SIZE_MB=10

# 人脸识别服务
FACE_API_KEY=${API_KEY}
FACE_PORT=8002
FACE_DATABASE_URL=sqlite:///data/faces.db
FACE_INDEX_FILE_PATH=/app/data/faces.index
FACE_RECOGNITION_THRESHOLD=0.6

# 视频分析服务
VIDEO_API_KEY=${API_KEY}
VIDEO_PORT=8003
REDIS_URL=redis://redis:6379
FACE_SERVICE_URL=http://face-service:8002
VIDEO_MAX_UPLOAD_SIZE_MB=100

# 监控
GRAFANA_ADMIN_PASSWORD=admin123
```

## 3. 生产环境部署

### 3.1 安全加固配置

创建生产环境专用的 Docker Compose 文件 `docker-compose.production.yml`：

```yaml
# docker-compose.production.yml
version: '3.8'

services:
  envoy-gateway:
    build: ./envoy
    ports:
      - "443:8080"   # TLS 加密端口
      - "9901:9901"   # 管理界面
    networks:
      - ai-network
    environment:
      - ENVOY_LOG_LEVEL=warn
    volumes:
      - ./envoy/envoy.yaml:/etc/envoy/envoy.yaml
      - ./ssl:/etc/ssl:ro  # TLS 证书
    restart: always
    # 资源限制
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: '0.5'
    # 健康检查
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9901/ready"]
      interval: 30s
      timeout: 5s
      retries: 3

  ocr-service:
    build: ./ocr-service
    networks:
      - ai-network
    environment:
      - API_KEY=${OCR_API_KEY}
      - LOG_LEVEL=WARNING
    volumes:
      - ocr-models:/app/models
      - ocr-logs:/app/logs
    restart: always
    deploy:
      resources:
        limits:
          memory: 2G  # OCR 模型需要较多内存
          cpus: '1.0'
        reservations:
          memory: 1G
    healthcheck:
      test: ["CMD", "python", "-c", "import requests; requests.get('http://localhost:8001/health', timeout=2) or exit(1)"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 30s  # 模型加载时间

  face-service:
    build: ./face-service
    networks:
      - ai-network
    environment:
      - API_KEY=${FACE_API_KEY}
      - LOG_LEVEL=WARNING
      - DATABASE_URL=sqlite:///data/faces.db
      - INDEX_FILE_PATH=/app/data/faces.index
    volumes:
      - face-data:/app/data  # 持久化存储
      - face-models:/app/models
      - face-logs:/app/logs
    restart: always
    deploy:
      resources:
        limits:
          memory: 4G  # InsightFace 模型需要大量内存
          cpus: '2.0'
        reservations:
          memory: 2G
    healthcheck:
      test: ["CMD", "python", "-c", "import requests; requests.get('http://localhost:8002/health', timeout=2) or exit(1)"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s  # FAISS 索引加载需要时间

  video-service:
    build: ./video-service
    networks:
      - ai-network
    environment:
      - API_KEY=${VIDEO_API_KEY}
      - LOG_LEVEL=WARNING
      - REDIS_URL=redis://redis:6379
      - FACE_SERVICE_URL=http://face-service:8002
    volumes:
      - video-temp:/tmp/video_processing
      - video-logs:/app/logs
    restart: always
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: '1.5'  # 视频处理需要 CPU
        reservations:
          memory: 512M
    healthcheck:
      test: ["CMD", "python", "-c", "import requests; requests.get('http://localhost:8003/health', timeout=3) or exit(1)"]
      interval: 30s
      timeout: 10s
      retries: 3

  redis:
    image: redis:7-alpine
    networks:
      - ai-network
    volumes:
      - redis-data:/data
    command: redis-server --appendonly yes --requirepass ${REDIS_PASSWORD}
    restart: always
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: '0.5'
    healthcheck:
      test: ["CMD", "redis-cli", "-a", "${REDIS_PASSWORD}", "ping"]
      interval: 30s
      timeout: 10s
      retries: 3

  # 监控服务配置保持不变...
```

### 3.2 启用 TLS 加密

#### 生成 TLS 证书

```bash
# 使用 Let's Encrypt 获取证书
certbot certonly --standalone -d your-domain.com

# 或使用自签名证书（仅测试）
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes
```

#### 配置 Envoy TLS 终止

更新 `envoy/envoy.yaml` 的监听器配置：

```yaml
listeners:
- name: https_listener
  address:
    socket_address:
      address: 0.0.0.0
      port_value: 8080
  filter_chains:
  - filter_chain_match:
      server_names: ["your-domain.com"]
    transport_socket:
      name: envoy.transport_sockets.tls
      typed_config:
        "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.DownstreamTlsContext
        common_tls_context:
          tls_certificates:
          - certificate_chain:
              filename: "/etc/ssl/cert.pem"
            private_key:
              filename: "/etc/ssl/key.pem"
    filters:
    - name: envoy.filters.network.http_connection_manager
      # ... 原有配置
```

### 3.3 数据持久化配置

#### 挂载持久化卷

```yaml
volumes:
  face-data:
    driver: local
    driver_opts:
      type: none
      device: /mnt/ai-storage/face-data
      o: bind

  ocr-models:
    driver: local
    driver_opts:
      type: none
      device: /mnt/ai-storage/ocr-models
      o: bind

  redis-data:
    driver: local
    driver_opts:
      type: none
      device: /mnt/ai-storage/redis-data
      o: bind

  prometheus-data:
    driver: local

  grafana-data:
    driver: local
```

#### 数据备份策略

```bash
# 人脸数据备份脚本
#!/bin/bash
BACKUP_DIR="/backups/face-data"
DATE=$(date +%Y%m%d_%H%M%S)

# 备份 SQLite 数据库
sqlite3 /mnt/ai-storage/face-data/faces.db ".backup $BACKUP_DIR/faces_$DATE.db"

# 备份 FAISS 索引
cp /mnt/ai-storage/face-data/faces.index $BACKUP_DIR/faces_$DATE.index

# 保留最近7天的备份
find $BACKUP_DIR -name "*.db" -mtime +7 -delete
find $BACKUP_DIR -name "*.index" -mtime +7 -delete
```

### 3.4 高可用部署（可选）

对于高可用需求，使用 `docker-compose.microservices-ha.yml`：

```bash
# 启动高可用版本
docker-compose -f docker-compose.microservices-ha.yml up -d

# 或使用脚本
./start-microservices-ha.sh
```

## 4. 监控与运维

### 4.1 监控仪表板

系统包含预配置的 Grafana 仪表板：

- **服务健康**：各服务状态、响应时间、错误率
- **资源使用**：CPU、内存、网络使用情况
- **业务指标**：API 调用统计、处理延迟、队列长度
- **AI 模型**：模型加载状态、推理时间、缓存命中率

访问地址：`http://<服务器IP>:3000` (用户名: admin, 密码: admin123)

### 4.2 告警配置

Prometheus 告警规则配置在 `monitoring/alerts.yml`：

```yaml
groups:
- name: ai-service-alerts
  rules:
  - alert: ServiceDown
    expr: up{job=~"ocr-service|face-service|video-service"} == 0
    for: 1m
    labels:
      severity: critical
    annotations:
      summary: "服务 {{ $labels.job }} 下线"
      description: "{{ $labels.job }} 服务已停止响应超过1分钟"

  - alert: HighMemoryUsage
    expr: (node_memory_MemTotal_bytes - node_memory_MemAvailable_bytes) / node_memory_MemTotal_bytes > 0.8
    for: 5m
    labels:
      severity: warning
    annotations:
      summary: "内存使用率过高"
      description: "内存使用率超过80%持续5分钟"

  - alert: HighErrorRate
    expr: rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) > 0.05
    for: 2m
    labels:
      severity: warning
    annotations:
      summary: "API 错误率过高"
      description: "5xx 错误率超过5%持续2分钟"
```

### 4.3 日志管理

配置集中式日志收集：

```yaml
# 在 docker-compose 中添加 ELK 或 Loki
services:
  loki:
    image: grafana/loki:latest
    ports:
      - "3100:3100"
    command: -config.file=/etc/loki/local-config.yaml

  promtail:
    image: grafana/promtail:latest
    volumes:
      - /var/log:/var/log
      - ./monitoring/promtail-config.yaml:/etc/promtail/config.yaml
```

## 5. 安全配置

### 5.1 API Key 管理

#### 多 API Key 支持

更新 Envoy 配置以支持多 API Key：

```lua
local valid_keys = {
  ["production-key-1"] = { rate_limit = 1000, services = {"ocr", "face", "video"} },
  ["production-key-2"] = { rate_limit = 100, services = {"ocr"} },
  ["backup-key"] = { rate_limit = 100, services = {"ocr", "face", "video"} }
}
```

#### Key 轮换策略

```bash
# 生成新 API Key
NEW_KEY=$(openssl rand -base64 32 | tr -d '=+/' | cut -c1-32)

# 更新配置文件
sed -i "s/old-api-key-here/$NEW_KEY/g" .env

# 重新部署服务
docker-compose -f docker-compose.production.yml up -d

# 通知客户端更新（保持旧key短期可用）
```

### 5.2 网络隔离

```yaml
networks:
  ai-network:
    driver: bridge
    internal: true  # 内部网络，不暴露到主机

  public-network:
    driver: bridge
    # 仅 Envoy 网关连接此网络
```

### 5.3 文件上传安全

- 文件类型验证（白名单）
- 文件大小限制
- 病毒扫描集成
- 临时文件定期清理

## 6. 性能优化

### 6.1 资源调整建议

| 场景 | OCR 服务 | 人脸识别服务 | 视频分析服务 |
|------|----------|--------------|--------------|
| 低负载 | 1 CPU, 2GB | 2 CPU, 4GB | 1 CPU, 1GB |
| 中等负载 | 2 CPU, 4GB | 4 CPU, 8GB | 2 CPU, 2GB |
| 高负载 | 4 CPU, 8GB | 8 CPU, 16GB | 4 CPU, 4GB |

### 6.2 缓存配置

系统已集成 Redis 缓存：

```python
# 使用缓存装饰器
from shared.cache import cache_result

@cache_result(ttl=3600, key_prefix="ocr_result")
def process_ocr(image_bytes):
    # OCR 处理逻辑
    pass
```

### 6.3 批量处理

利用批量 API 提高吞吐量：

```bash
# 批量人脸检测
curl -X POST http://localhost:8080/v1/face/detect-batch \
  -H "x-api-key: $API_KEY" \
  -F "files=@face1.jpg" \
  -F "files=@face2.jpg" \
  -F "files=@face3.jpg"
```

## 7. 故障排除

### 7.1 常见问题

#### 服务启动失败

```bash
# 查看服务日志
docker-compose logs [service-name]

# 检查端口冲突
netstat -tulpn | grep :8080

# 验证 Docker 资源
docker system df
docker stats
```

#### 内存不足

```bash
# 监控内存使用
docker stats --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}"

# 清理未使用的资源
docker system prune -a

# 调整服务内存限制
# 在 docker-compose.yml 中增加内存限制
```

#### API 网关问题

```bash
# 检查 Envoy 配置
docker exec [envoy-container] envoy --mode validate -c /etc/envoy/envoy.yaml

# 查看路由状态
curl http://localhost:9901/config_dump | jq '.configs[1].dynamic_active_clusters'
```

### 7.2 健康检查端点

| 服务 | 健康检查 URL | 预期响应 |
|------|--------------|----------|
| Envoy 网关 | `http://localhost:9901/ready` | `LIVE` |
| OCR 服务 | `http://localhost:8001/health` | `{"status":"healthy"}` |
| 人脸识别 | `http://localhost:8002/health` | `{"status":"healthy"}` |
| 视频分析 | `http://localhost:8003/health` | `{"status":"healthy"}` |
| Redis | `redis-cli ping` | `PONG` |

## 8. 备份与恢复

### 8.1 定期备份

```bash
# 完整备份脚本
#!/bin/bash
BACKUP_DIR="/backups/ai-service"
DATE=$(date +%Y%m%d)

# 创建备份目录
mkdir -p $BACKUP_DIR/$DATE

# 备份数据库文件
cp -r /mnt/ai-storage/face-data $BACKUP_DIR/$DATE/
cp -r /mnt/ai-storage/ocr-models $BACKUP_DIR/$DATE/

# 备份 Docker Compose 配置
cp docker-compose.production.yml $BACKUP_DIR/$DATE/
cp .env $BACKUP_DIR/$DATE/.env.backup

# 备份监控数据（可选）
docker exec prometheus tar czf - /prometheus | gzip > $BACKUP_DIR/$DATE/prometheus-data.tar.gz

# 上传到云存储（可选）
aws s3 sync $BACKUP_DIR/$DATE s3://your-bucket/ai-service-backups/$DATE/
```

### 8.2 灾难恢复

```bash
# 恢复步骤
1. 安装 Docker 和 Docker Compose
2. 从备份恢复数据文件
3. 复制配置文件和证书
4. 启动服务：docker-compose -f docker-compose.production.yml up -d
5. 验证服务健康状态
```

## 9. 升级与维护

### 9.1 服务升级

```bash
# 滚动更新策略
docker-compose -f docker-compose.production.yml pull
docker-compose -f docker-compose.production.yml up -d --force-recreate --no-deps [service-name]

# 验证升级
docker-compose -f docker-compose.production.yml ps
curl http://localhost:8080/health
```

### 9.2 模型更新

```bash
# 更新 OCR 模型
1. 将新模型文件放入 ./ocr-service/models/
2. 重启 OCR 服务
3. 验证识别准确性

# 更新人脸识别模型
1. 停止 face-service
2. 备份现有数据和索引
3. 更新模型文件
4. 重新初始化 FAISS 索引
5. 重启服务
```

## 10. 联系支持

### 问题报告

- **GitHub Issues**: [项目 Issues 页面]
- **监控告警**: 通过 Prometheus/Grafana 告警
- **技术支持**: [联系邮箱/电话]

### 紧急响应

1. 服务不可用：检查 Docker 容器状态和日志
2. 性能下降：监控资源使用情况，考虑扩展
3. 安全事件：立即轮换 API Key，检查访问日志

---

**文档版本**: 1.0
**最后更新**: 2026-03-03
**维护团队**: AI Service 运维团队
**状态**: 正式发布

## 附录

### A. 端口说明

| 端口 | 服务 | 协议 | 用途 | 对外暴露 |
|------|------|------|------|----------|
| 8080 | Envoy | HTTP/HTTPS | API 网关 | 是 |
| 9901 | Envoy | HTTP | 管理界面 | 否（建议） |
| 8001 | OCR | HTTP | OCR 服务 | 否 |
| 8002 | Face | HTTP | 人脸识别 | 否 |
| 8003 | Video | HTTP | 视频分析 | 否 |
| 6379 | Redis | TCP | 任务队列 | 否 |
| 9090 | Prometheus | HTTP | 监控 | 否（建议） |
| 3000 | Grafana | HTTP | 仪表板 | 否（建议） |

### B. 性能基准

| 场景 | 平均响应时间 | 吞吐量 (RPS) | 资源消耗 |
|------|--------------|--------------|----------|
| OCR 文字识别 | 200-500ms | 50-100 | 1 CPU, 500MB |
| 人脸检测 | 100-300ms | 30-50 | 2 CPU, 1GB |
| 人脸识别 | 300-800ms | 20-30 | 2 CPU, 2GB |
| 视频分析 | 10-60s | 1-5 | 2 CPU, 1GB |

### C. 相关文档

- [AI Service 实施计划](./ai-service-implementation-plan.md)
- [AI Service 用户手册](./ai-service-user-manual.md)
- [AI Service 优化指南](./ai-service-optimization.md)
- [AI Service 架构重构](./ai-service-refactoring.md)