# 视频人脸识别集成方案分析

本文档分析了 Immich 当前的视频处理能力，并提出了实现“视频人脸识别”的三种技术集成方案。

## 1. 现状分析

目前 Immich **不支持** 原生的视频人脸识别。

*   **当前机制**:
    *   上传视频后，系统使用 FFmpeg 提取 **一张** 代表性的预览图 (Thumbnail)。
    *   人脸识别任务 (`AssetDetectFaces`) 仅针对这张 **静态预览图** 进行。
    *   **局限性**: 如果预览图未捕捉到人脸（例如人脸出现在视频中段），则该视频无法被识别到人物。

---

## 2. 集成方案

为了实现对视频内容的完整人脸识别，建议采用以下三种方案之一：

### 方案 A: 抽帧 + 现有 ML 服务 (推荐 - 成本最低)

利用 Immich 现有的基础设施，通过增加“抽帧”步骤来实现。

1.  **流程改造**:
    *   在 `Microservices` 中新增一个 `VideoFrameExtractor` 任务。
    *   使用 `ffmpeg` 每隔 N 秒（如 5秒）提取一帧。
    *   将提取的帧作为 **临时图片** 发送给现有的 `facial-recognition` 接口。
2.  **数据存储**:
    *   需要修改数据库 `asset_face` 表，增加 `timestamp` (时间戳) 字段，以记录人脸出现的具体时间。
3.  **优点**: 复用现有 ML 服务，开发量适中。
4.  **缺点**: 数据量激增（1分钟视频可能产生 12 张图片），数据库压力大。

### 方案 B: 独立视频分析服务 (推荐 - 性能最佳)

构建一个独立的 Video Analysis Service，专门处理视频流。

1.  **技术栈**: Python + OpenCV + FFmpeg。
2.  **流程**:
    *   服务直接读取视频文件流。
    *   使用 OpenCV 实时解码并检测人脸（跳帧检测，如每 10 帧检测一次）。
    *   仅当检测到人脸时，才提取特征向量并去重（避免同一人在相邻帧重复记录）。
    *   最终输出：`[{ "personId": "张三", "timestamp": 12.5 }, ...]`。
3.  **优点**: 性能极高，不产生大量临时文件，结果精准。
4.  **缺点**: 开发成本高，需要独立部署。

### 方案 C: 云端 API 集成 (最快落地)

如果不想自己维护复杂的视频处理管道，可以对接公有云 API。

1.  **服务商**: 阿里云/腾讯云/AWS Rekognition 的“视频人脸分析”接口。
2.  **流程**:
    *   上传视频到云端对象存储 (OSS/S3)。
    *   调用云端 API 进行分析。
    *   获取 JSON 结果并存入 Immich 数据库。
3.  **优点**: 零开发，精度最高（支持侧脸、遮挡）。
4.  **缺点**: **成本高昂**（按分钟计费），隐私数据出域。

---

## 3. 实施建议

对于家庭/个人自托管场景，**方案 B (独立视频分析服务)** 是最佳选择。

### 3.1 独立服务架构设计

建议开发一个轻量级的 `immich-video-analyzer` 容器：

*   **输入**: 视频文件路径 (只读挂载)。
*   **处理**:
    ```python
    import cv2
    cap = cv2.VideoCapture(video_path)
    while cap.isOpened():
        ret, frame = cap.read()
        if frame_count % 30 == 0:  # 每秒处理一帧
            faces = face_detector.detect(frame)
            if faces:
                embeddings = face_recognizer.extract(frame, faces)
                # 调用 Immich 内部 API 进行匹配
                results = match_faces(embeddings)
                save_result(timestamp, results)
    ```
*   **输出**: 更新 Immich 数据库，标记该视频包含的人物。

### 3.2 数据库变更

需要在 `asset_face` 表中增加时间维度，或新建 `asset_video_face` 表：

```sql
CREATE TABLE asset_video_face (
  id UUID PRIMARY KEY,
  assetId UUID REFERENCES assets(id),
  personId UUID REFERENCES people(id),
  timestamp FLOAT, -- 人脸出现的时间点 (秒)
  boundingBox JSONB -- 人脸位置
);
```

通过这种方式，您不仅能知道视频里有谁，将来还能实现“点击头像跳转到视频中他出现的片段”的高级功能。
