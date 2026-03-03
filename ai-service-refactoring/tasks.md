# Tasks

- [x] Task 1: 初始化独立 AI 服务项目结构
  - [x] SubTask 1.1: 创建 `ai-service` 目录及基础 FastAPI 项目结构
  - [x] SubTask 1.2: 配置 `requirements.txt` (FastAPI, OpenCV, InsightFace, RapidOCR, Faiss/SQLite-vss)
  - [x] SubTask 1.3: 创建独立的 `Dockerfile` 和 `docker-compose.yml`

- [x] Task 2: 实现 OCR 功能模块
  - [x] SubTask 2.1: 集成 RapidOCR 库
  - [x] SubTask 2.2: 实现 `/v1/ocr/scan` 接口
  - [x] SubTask 2.3: 实现接口鉴权中间件

- [x] Task 3: 实现人脸识别功能模块
  - [x] SubTask 3.1: 集成 InsightFace 库 (检测+识别)
  - [x] SubTask 3.2: 集成向量数据库 (Faiss 或 SQLite-vss)
  - [x] SubTask 3.3: 实现 `/v1/face/register` 接口 (特征提取 + 存储)
  - [x] SubTask 3.4: 实现 `/v1/face/recognize` 接口 (特征提取 + 搜索)

- [x] Task 4: 实现视频分析功能模块
  - [x] SubTask 4.1: 实现视频流读取与跳帧逻辑 (OpenCV)
  - [x] SubTask 4.2: 复用人脸识别模块进行特征提取
  - [x] SubTask 4.3: 实现视频人脸分析流程 (检测 -> 识别 -> 记录)
  - [x] SubTask 4.4: 实现 `/v1/video/analyze` 接口及异步任务处理

- [x] Task 5: 测试与验证
  - [x] SubTask 5.1: 编写单元测试
  - [x] SubTask 5.2: 验证 OCR 功能 (使用测试图片)
  - [x] SubTask 5.3: 验证人脸注册与识别功能 (使用测试图片)
  - [x] SubTask 5.4: 验证视频分析功能 (使用测试视频)

# Task Dependencies
- [Task 2] depends on [Task 1]
- [Task 3] depends on [Task 1]
- [Task 4] depends on [Task 3]
- [Task 5] depends on [Task 2], [Task 3], [Task 4]
