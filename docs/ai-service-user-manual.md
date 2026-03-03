# AI Service 用户手册

## 概述

Immich AI Service 是一个独立的机器学习服务，提供 OCR 文字识别、人脸识别和视频分析功能。该服务基于 FastAPI 构建，支持 Docker 部署，可通过 RESTful API 调用。

### 主要功能

1. **OCR 文字识别**：识别图像中的文字，返回文本内容和坐标
2. **人脸识别**：支持人脸注册和识别，基于 InsightFace 和 FAISS 向量搜索
3. **视频分析**：分析视频文件中的人脸出现情况，返回时间戳和识别结果

### 技术架构

- **Web 框架**: FastAPI
- **OCR 引擎**: RapidOCR (基于 ONNX Runtime)
- **人脸识别**: InsightFace (Buffalo_L 模型)
- **向量搜索**: FAISS
- **异步处理**: BackgroundTasks (视频分析)
- **认证**: API Key 验证

## 快速开始

### 1. 环境要求

- Python 3.10+
- Docker (可选)
- 至少 2GB 内存
- 磁盘空间：模型文件约 300MB

### 2. 安装与运行

#### 使用 Docker (推荐)

```bash
# 克隆仓库
git clone https://github.com/immich-app/immich.git
cd immich/ai-service

# 构建并运行
docker-compose up --build
```

服务将在 `http://localhost:8000` 启动。

#### 手动安装

```bash
# 安装依赖
pip install -r requirements.txt

# 下载模型
# 模型已包含在仓库中，位于 models/ 目录

# 启动服务
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 3. 配置说明

#### 环境变量

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| API_KEY | your-secret-api-key | API 认证密钥 |
| PORT | 8000 | 服务端口 |

#### 模型配置

- OCR 模型：RapidOCR 自动下载
- 人脸识别模型：Buffalo_L，存储在 `models/models/buffalo_l/`
- 向量索引：内存存储，重启后丢失

## API 参考

所有 API 请求都需要在 Header 中包含 `x-api-key`。

### 通用响应格式

#### 成功响应
```json
{
  "results": [...]
}
```

#### 错误响应
```json
{
  "detail": "错误描述"
}
```

### 状态码

- 200：成功
- 400：请求参数错误
- 401：认证失败
- 404：资源不存在
- 500：服务器内部错误

---

### 1. OCR 文字识别

识别图像中的文字内容。

**端点**: `POST /v1/ocr/scan`

**请求**:
- Header: `x-api-key: <your-api-key>`
- Content-Type: `multipart/form-data`
- Body: `file` (图像文件)

**响应**:
```json
{
  "results": [
    {
      "text": "识别到的文字",
      "confidence": 0.95,
      "coordinates": [[x1, y1], [x2, y2], [x3, y3], [x4, y4]]
    }
  ]
}
```

**示例**:
```bash
curl -X POST http://localhost:8000/v1/ocr/scan \
  -H "x-api-key: your-secret-api-key" \
  -F "file=@sample_text.png"
```

---

### 2. 人脸识别

#### 2.1 注册人脸

注册新的人脸到系统中。

**端点**: `POST /v1/face/register`

**请求**:
- Header: `x-api-key: <your-api-key>`
- Content-Type: `multipart/form-data`
- Body:
  - `name`: 人名 (表单字段)
  - `file`: 包含人脸的图像文件

**响应**:
```json
{
  "message": "Face registered for <name>",
  "face_count": 1
}
```

**示例**:
```bash
curl -X POST http://localhost:8000/v1/face/register \
  -H "x-api-key: your-secret-api-key" \
  -F "name=张三" \
  -F "file=@sample_face.jpg"
```

#### 2.2 识别人脸

识别图像中的人脸。

**端点**: `POST /v1/face/recognize`

**请求**:
- Header: `x-api-key: <your-api-key>`
- Content-Type: `multipart/form-data`
- Body: `file` (包含人脸的图像文件)

**响应**:
```json
{
  "name": "张三",
  "distance": 0.35
}
```

**说明**:
- `distance`: 向量距离，值越小表示匹配度越高
- 如果未注册任何人脸，返回错误
- 如果检测到多个人脸，只识别最大的一个

**示例**:
```bash
curl -X POST http://localhost:8000/v1/face/recognize \
  -H "x-api-key: your-secret-api-key" \
  -F "file=@sample_face.jpg"
```

---

### 3. 视频分析

异步分析视频文件中的人脸出现情况。

#### 3.1 提交分析任务

**端点**: `POST /v1/video/analyze`

**请求**:
- Header: `x-api-key: <your-api-key>`
- Content-Type: `multipart/form-data`
- Body: `file` (视频文件)

**响应**:
```json
{
  "job_id": "uuid-v4-string"
}
```

#### 3.2 查询任务状态

**端点**: `GET /v1/video/status/{job_id}`

**请求**:
- Header: `x-api-key: <your-api-key>`
- Path Parameter: `job_id` (任务ID)

**响应状态**:
- `processing`: 处理中
- `completed`: 完成
- `failed`: 失败

**完成时的响应**:
```json
{
  "status": "completed",
  "results": [
    {
      "timestamp": 1.5,
      "person_name": "张三",
      "confidence": 0.42
    }
  ]
}
```

**失败时的响应**:
```json
{
  "status": "failed",
  "error": "错误描述"
}
```

**示例**:
```bash
# 提交分析
curl -X POST http://localhost:8000/v1/video/analyze \
  -H "x-api-key: your-secret-api-key" \
  -F "file=@sample_video.mp4"

# 查询状态
curl -X GET http://localhost:8000/v1/video/status/{job_id} \
  -H "x-api-key: your-secret-api-key"
```

**说明**:
- 视频分析是异步处理，每秒分析一帧
- 结果包含时间戳（秒）、人名和置信度（距离）
- 临时视频文件在处理后自动删除

---

## 测试与验证

### 内置测试脚本

项目包含完整的测试脚本，验证所有功能：

```bash
cd ai-service
python tests/test_all_features.py
```

测试脚本会：
1. 自动启动服务
2. 创建测试图像和视频
3. 测试所有 API 端点
4. 验证 OCR、人脸识别和视频分析功能

### 手动测试

#### 准备测试文件

1. **人脸图像**: `sample_face.jpg` (已提供)
2. **文字图像**: `sample_text.png` (测试时自动创建)
3. **测试视频**: `sample_video.mp4` (测试时自动创建)

#### 测试步骤

1. 启动服务
2. 注册测试人脸
3. 测试人脸识别
4. 测试 OCR
5. 测试视频分析

## 部署指南

### Docker 部署

#### 单机部署
```bash
docker-compose up -d
```

#### 生产环境建议

1. **配置持久化存储**: 修改 `docker-compose.yml` 添加数据卷
2. **设置强密码**: 修改 `API_KEY` 环境变量
3. **启用 HTTPS**: 使用反向代理 (Nginx, Traefik)
4. **监控与日志**: 配置日志收集和监控

### Kubernetes 部署

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ai-service
spec:
  replicas: 2
  selector:
    matchLabels:
      app: ai-service
  template:
    metadata:
      labels:
        app: ai-service
    spec:
      containers:
      - name: ai-service
        image: immich/ai-service:latest
        ports:
        - containerPort: 8000
        env:
        - name: API_KEY
          valueFrom:
            secretKeyRef:
              name: ai-service-secrets
              key: api-key
        resources:
          requests:
            memory: "2Gi"
            cpu: "500m"
          limits:
            memory: "4Gi"
            cpu: "2000m"
```

## 故障排除

### 常见问题

#### 1. 服务无法启动
- **问题**: 端口被占用
- **解决**: 修改端口 `--port 8001`

#### 2. 模型加载失败
- **问题**: 模型文件损坏或缺失
- **解决**: 删除 `models/models/` 目录重新下载

#### 3. 内存不足
- **问题**: 处理大视频时内存溢出
- **解决**: 增加系统内存或限制视频大小

#### 4. 人脸识别不准确
- **问题**: 图像质量差或角度不佳
- **解决**: 使用正面清晰的人脸图像

### 日志查看

```bash
# Docker 日志
docker-compose logs -f ai-service

# 手动运行日志
uvicorn app.main:app --host 0.0.0.0 --port 8000 --log-level debug
```

## 性能优化

### 硬件建议

- **CPU**: 4核以上
- **内存**: 4GB 以上
- **存储**: SSD 推荐

### 配置调优

1. **批处理**: 支持批量图像处理
2. **缓存**: 实现结果缓存
3. **模型量化**: 使用量化模型减少内存占用

## 安全注意事项

1. **API Key 保护**: 不要泄露 API Key
2. **输入验证**: 服务已实现基本的文件类型验证
3. **资源限制**: 建议配置文件大小限制
4. **网络隔离**: 生产环境应部署在内网

## 开发指南

### 项目结构

```
ai-service/
├── app/
│   ├── main.py          # FastAPI 主应用
│   ├── ocr.py           # OCR 功能
│   ├── face.py          # 人脸识别功能
│   └── video.py         # 视频分析功能
├── models/              # 模型文件
├── tests/               # 测试文件
├── requirements.txt     # Python 依赖
├── Dockerfile          # Docker 配置
└── docker-compose.yml  # Docker Compose 配置
```

### 添加新功能

1. 在 `app/` 目录创建新模块
2. 在 `main.py` 中添加路由
3. 更新 `requirements.txt`
4. 添加测试用例

### 代码规范

- 使用类型提示
- 添加文档字符串
- 遵循 PEP 8 规范

## 版本历史

### v1.0.0 (当前)
- OCR 文字识别
- 人脸注册与识别
- 视频人脸分析
- API Key 认证
- Docker 支持

## 支持与贡献

### 问题报告

在 GitHub Issues 报告问题，包括：
1. 问题描述
2. 复现步骤
3. 环境信息
4. 日志输出

### 贡献代码

1. Fork 仓库
2. 创建功能分支
3. 提交 Pull Request
4. 通过代码审查

## 许可证

[根据项目许可证填写]