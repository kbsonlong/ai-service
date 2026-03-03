# AI Service 微服务架构

## 概述

此项目基于 Envoy 网关的微服务架构，包含以下服务：

1. **Envoy Gateway** (端口 8080) - API 网关，负责路由、认证和负载均衡
2. **OCR Service** (端口 8001) - 文字识别服务
3. **Face Recognition Service** (端口 8002) - 人脸识别服务
4. **Video Analysis Service** (端口 8003) - 视频分析服务
5. **Redis** (端口 6379) - 任务队列存储
6. **RQ Worker** - 异步任务处理工作进程

## 架构特点

- **服务解耦**：每个功能模块独立部署和扩展
- **统一网关**：使用 Envoy 作为 API 网关，避免重复造轮子
- **独立运行**：各服务可独立启动和测试
- **异步处理**：视频分析使用 Redis + RQ 实现异步任务队列
- **生产就绪**：包含健康检查、监控、日志等生产级特性

## 快速开始

### 1. 启动所有服务

```bash
# 使用启动脚本（推荐）
./start-microservices.sh up

# 或直接使用 Docker Compose
docker-compose -f docker-compose.microservices.yml up -d
```

### 2. 检查服务状态

```bash
./start-microservices.sh status
```

### 3. 运行基本测试

```bash
./start-microservices.sh test
```

### 4. 查看日志

```bash
./start-microservices.sh logs
```

### 5. 停止服务

```bash
./start-microservices.sh down
```

## 服务端点

### 通过 Envoy 网关访问（推荐）
```
http://localhost:8080/v1/ocr/scan      # OCR文字识别
http://localhost:8080/v1/face/register  # 人脸注册
http://localhost:8080/v1/face/recognize # 人脸识别
http://localhost:8080/v1/video/analyze  # 视频分析
```

### 直接访问各服务
```
OCR服务:      http://localhost:8001
人脸识别服务: http://localhost:8002
视频分析服务: http://localhost:8003
```

### 管理界面
```
Envoy管理界面: http://localhost:9901
Prometheus:    http://localhost:9090
Grafana:       http://localhost:3000 (admin/admin)
```

## API 使用示例

### OCR 文字识别

```bash
curl -X POST http://localhost:8080/v1/ocr/scan \
  -H "x-api-key: your-secret-api-key" \
  -F "file=@sample_text.png"
```

### 人脸注册

```bash
curl -X POST http://localhost:8080/v1/face/register \
  -H "x-api-key: your-secret-api-key" \
  -F "name=张三" \
  -F "file=@sample_face.jpg"
```

### 人脸识别

```bash
curl -X POST http://localhost:8080/v1/face/recognize \
  -H "x-api-key: your-secret-api-key" \
  -F "file=@sample_face.jpg"
```

### 视频分析（异步）

```bash
# 提交分析任务
curl -X POST http://localhost:8080/v1/video/analyze \
  -H "x-api-key: your-secret-api-key" \
  -F "file=@sample_video.mp4"

# 查询任务状态（替换 {task_id}）
curl -X GET http://localhost:8080/v1/video/status/{task_id} \
  -H "x-api-key: your-secret-api-key"
```

## 项目结构

```
ai-service/
├── envoy/                    # Envoy网关配置
│   ├── Dockerfile
│   └── envoy.yaml           # Envoy配置文件
├── ocr-service/              # OCR微服务
│   ├── app/
│   │   ├── main.py          # 主应用
│   │   └── ocr_engine.py    # OCR引擎
│   ├── Dockerfile
│   └── requirements.txt
├── face-service/             # 人脸识别微服务
│   ├── app/
│   │   ├── main.py          # 主应用
│   │   ├── database.py      # 数据库管理
│   │   └── face_engine.py   # 人脸识别引擎
│   ├── data/                # 数据目录（自动创建）
│   ├── Dockerfile
│   └── requirements.txt
├── video-service/            # 视频分析微服务
│   ├── app/
│   │   ├── main.py          # 主应用
│   │   ├── task_queue.py    # 任务队列
│   │   └── video_analyzer.py # 视频分析器
│   ├── Dockerfile
│   └── requirements.txt
├── shared/                   # 共享模块
│   ├── config.py            # 配置管理
│   ├── utils.py             # 工具函数
│   └── exceptions.py        # 异常处理
├── docker-compose.microservices.yml  # Docker Compose配置
├── start-microservices.sh   # 启动脚本
└── MICROSERVICES_README.md  # 本文件
```

## 配置说明

### 环境变量

各服务支持以下环境变量：

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| API_KEY | your-secret-api-key | API认证密钥 |
| HOST | 0.0.0.0 | 服务监听地址 |
| PORT | 服务特定端口 | 服务端口 |
| LOG_LEVEL | INFO | 日志级别 |
| MODELS_DIR | ./models | 模型文件目录 |
| DATABASE_URL | sqlite:///data/faces.db | 数据库URL（人脸服务） |
| REDIS_URL | redis://redis:6379 | Redis连接URL（视频服务） |
| FACE_SERVICE_URL | http://face-service:8002 | 人脸服务URL（视频服务） |

### 修改配置

1. **修改API密钥**：在 `docker-compose.microservices.yml` 中修改 `API_KEY` 环境变量
2. **调整资源限制**：在 Docker Compose 文件中修改资源限制
3. **自定义模型路径**：通过 `MODELS_DIR` 环境变量指定模型目录

## 开发说明

### 独立运行单个服务

```bash
# OCR服务
cd ocr-service
uvicorn app.main:app --host 0.0.0.0 --port 8001

# 人脸识别服务
cd face-service
uvicorn app.main:app --host 0.0.0.0 --port 8002

# 视频分析服务
cd video-service
uvicorn app.main:app --host 0.0.0.0 --port 8003
```

### 构建单个服务

```bash
# OCR服务
cd ocr-service
docker build -t ocr-service:latest .

# 人脸识别服务
cd face-service
docker build -t face-service:latest .

# 视频分析服务
cd video-service
docker build -t video-service:latest .

# Envoy网关
cd envoy
docker build -t envoy-gateway:latest .
```

### 添加新功能

1. **添加新服务**：复制现有服务模板，修改业务逻辑
2. **扩展现有服务**：在对应的服务中添加新端点
3. **修改网关路由**：更新 `envoy/envoy.yaml` 中的路由配置

## 故障排除

### 常见问题

1. **服务启动失败**
   - 检查端口是否被占用
   - 检查Docker和Docker Compose版本
   - 查看服务日志：`./start-microservices.sh logs`

2. **模型加载失败**
   - 确保模型文件存在
   - 检查模型文件权限
   - 查看服务日志了解具体错误

3. **API调用返回401**
   - 检查请求头中的 `x-api-key`
   - 确保与 `API_KEY` 环境变量一致

4. **视频分析任务卡住**
   - 检查Redis是否正常运行
   - 检查RQ工作进程日志
   - 确保人脸识别服务可用

### 查看日志

```bash
# 查看所有服务日志
./start-microservices.sh logs

# 查看特定服务日志
docker-compose -f docker-compose.microservices.yml logs ocr-service
docker-compose -f docker-compose.microservices.yml logs face-service
docker-compose -f docker-compose.microservices.yml logs video-service
docker-compose -f docker-compose.microservices.yml logs envoy-gateway
```

### 健康检查

```bash
# 手动检查服务健康状态
curl http://localhost:8001/health
curl http://localhost:8002/health
curl http://localhost:8003/health
curl http://localhost:8080/health
```

## 监控和运维

### Prometheus 指标

各服务暴露 Prometheus 指标端点：
- OCR服务: `http://localhost:8001/metrics`
- 人脸识别服务: `http://localhost:8002/metrics`
- 视频分析服务: `http://localhost:8003/metrics`

### Grafana 仪表板

访问 `http://localhost:3000` 使用 Grafana：
- 用户名: `admin`
- 密码: `admin`

预配置的仪表板包括：
- 服务健康状态
- API请求统计
- 处理延迟监控
- 资源使用情��

## 下一步计划

### 第一阶段完成
- [x] Envoy网关配置
- [x] 服务拆分和独立部署
- [x] 基本功能测试
- [x] Docker Compose编排

### 第二阶段计划
- [ ] 数据持久化（FAISS索引文件）
- [ ] 多实例负载均衡
- [ ] 高级监控和告警
- [ ] API文档自动生成

### 第三阶段计划
- [ ] Kubernetes部署配置
- [ ] 服务发现和注册
- [ ] 分布式追踪
- [ ] 自动扩缩容

## 联系方式

如有问题，请查看项目文档或联系开发团队。

---

**版本**: 1.0.0
**最后更新**: 2026-03-02
**状态**: 第一阶段实施完成
