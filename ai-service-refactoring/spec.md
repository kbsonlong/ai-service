# AI 服务重构与独立视频分析服务 Spec

## Why
目前 Immich 的 OCR 和人脸识别功能与主服务耦合较紧，无法作为通用 AI 服务供外部应用（如智能家居、商品扫描）使用。此外，视频人脸识别功能目前仅支持封面图，无法分析视频内容。为了提升系统的复用性、灵活性，并增强视频分析能力，需要对 AI 服务进行重构，并引入独立的视频分析服务。

## What Changes
- **新建 `ai-service` 独立项目**:
    - 基于 FastAPI 构建，作为一个完全独立的服务，不依赖 Immich 的任何基础设施。
    - 参考 Immich ML 服务的代码逻辑，集成 OCR 和人脸识别能力。
    - 实现 API 鉴权（API Key）。
- **功能模块**:
    - **OCR**: 提供 `/v1/ocr/scan` 接口，接收图片并返回识别出的文字及坐标，内部集成 RapidOCR。
    - **人脸识别**: 
        - 提供 `/v1/face/register` 接口，接收图片和人名，提取特征并存入本地向量库（SQLite-vss 或 Faiss）。
        - 提供 `/v1/face/recognize` 接口，接收图片，提取特征并在向量库中搜索最相似的人脸，返回人名和置信度。
        - 内部集成 InsightFace。
    - **视频分析**:
        - 提供 `/v1/video/analyze` 接口，接收视频文件（或流地址），进行人脸检测与识别。
        - 使用 OpenCV 读取视频流，跳帧检测，调用人脸识别模块提取特征并记录结果。
- **部署方式**:
    - 提供独立的 `Dockerfile` 和 `docker-compose.yml`，可单机部署。

## Impact
- **Affected specs**: 无
- **Affected code**: 无（完全独立的新项目）
- **New Artifacts**:
    - `ai-service` 源代码目录（包含 FastAPI 应用、模型加载、业务逻辑）。
    - 独立的 `requirements.txt` 和 `Dockerfile`。
    - API 文档。

## ADDED Requirements
### Requirement: AI Service (Standalone)
系统 SHALL 提供一个独立的 HTTP API 服务，具备以下能力：
- **鉴权**: 支持通过 `X-API-Key` 头进行请求验证。
- **OCR**: 提供 `/v1/ocr/scan` 接口，接收图片并返回识别出的文字及坐标。
- **人脸识别闭环**:
    - 提供 `/v1/face/register` 接口，接收图片和人名，提取特征并存入本地向量库。
    - 提供 `/v1/face/recognize` 接口，接收图片，提取特征并在向量库中搜索最相似的人脸，返回人名和置信度。
- **视频分析**:
    - 提供 `/v1/video/analyze` 接口，接收视频文件，分析其中出现的人脸及其时间点。
    - 支持异步任务处理（视频分析可能耗时较长）。

#### Scenario: 独立部署
- **WHEN** 用户部署该服务
- **THEN** 服务启动并监听端口，可通过 API Key 访问 OCR、人脸识别及视频分析功能，无需 Immich 环境。

## MODIFIED Requirements
无（不再修改 Immich 的 docker-compose.yml）

## REMOVED Requirements
### Requirement: Docker 部署
不再修改 Immich 的 `docker-compose.yml`，而是提供独立的部署文件。
