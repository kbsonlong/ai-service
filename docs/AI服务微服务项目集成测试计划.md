# AI服务微服务项目集成测试计划

## 项目概述

AI服务微服务项目是一个将单体AI应用拆分为多个独立服务的架构，包含OCR服务、人脸识别服务、视频分析服务、Envoy
API网关、Redis任务队列、RQ工作进程以及完整的监控栈（Prometheus+Grafana）。目前已有基础端到端测试，但需要建立完整的集成测试体系以支持生产环境部署。

## 现有测试分析

### 优势

- 已有端到端集成测试（test_all_features.py等）
- 测试覆盖主要API端点（OCR、人脸识别、视频分析）
- 自动生成测试数据（图像、视频）
- 包含认证测试和错误处理

### 不足

- 缺乏标准测试框架（未使用pytest/unittest）
- 测试直接启动uvicorn服务器，而非使用docker-compose环境
- 配置硬编码在测试文件中
- 无单元测试和集成测试分层
- 无测试报告和代码覆盖率统计
- 无CI/CD集成

## 集成测试计划目标

1. 建立三层测试架构：单元测试、集成测试、端到端测试
2. 使用docker-compose构建测试环境
3. 标准化测试框架和工具链
4. 实现自动化CI/CD集成测试
5. 建立监控和性能测试体系
6. 提供详细的测试报告和质量指标

## 实施阶段

### 阶段1：测试基础设施搭建（1-2周）

关键文件创建

1. docker-compose.test.yml - 测试专用docker-compose配置
  - 路径：/Users/zengshenglong/Code/PyWorkSpace/immich/ai-service/docker-compose.test.yml
  - 包含所有微服务+测试运行器容器
  - 测试专用环境变量配置
2. pytest.ini - pytest测试框架配置
  - 路径：/Users/zengshenglong/Code/PyWorkSpace/immich/ai-service/pytest.ini
  - 配置测试标记（unit/integration/e2e/performance）
  - 配置测试报告输出（HTML/XML）
  - 配置代码覆盖率收集
3. 测试数据目录结构
test_data/
├── images/
│   ├── ocr/          # OCR测试图像
│   └── faces/        # 人脸测试图像
├── videos/           # 视频测试文件
└── fixtures/         # 预置测试数据
4. 基础测试工具类
  - tests/utils/test_data_generator.py - 测试数据生成工具
  - tests/utils/metrics_collector.py - 性能指标收集工具
  - tests/utils/service_health.py - 服务健康检查工具

### 阶段2：测试用例设计与迁移（2-3周）

三层测试架构

1. 单元测试层（各微服务内部）
  - 位置：{service_name}/tests/unit/
  - 测试业务逻辑、数据验证、模型推理
  - 使用unittest.mock隔离外部依赖
2. 集成测试层（服务间通信）
  - 位置：tests/integration/
  - 测试API调用、数据库交互、Redis队列
  - 验证服务间数据流和错误处理
3. 端到端测试层（完整流程）
  - 位置：tests/e2e/
  - 测试完整用户场景、网关路由、监控集成
  - 迁移现有测试脚本到pytest格式

测试用例类型

1. API测试 - 验证所有RESTful API端点
2. 功能测试 - 验证业务逻辑和数据处理
3. 性能测试 - 验证并发处理能力和响应时间
4. 容错测试 - 验证服务降级和故障恢复
5. 安全测试 - 验证认证、授权和输入验证
6. 监控测试 - 验证指标收集和告警触发

### 阶段3：CI/CD集成（1周）

GitHub Actions工作流

- 路径：.github/workflows/test.yml
- 触发条件：push到main/develop分支、pull_request
- 执行步骤：
  a. 启动测试环境（docker-compose.test.yml）
  b. 等待服务健康检查
  c. 执行三层测试套件
  d. 生成测试报告和覆盖率报告
  e. 上传测试结果作为Artifact
  f. 清理测试环境

质量门禁

- 单元测试覆盖率不低于80%
- 集成测试通过率100%
- 端到端测试通过率95%以上
- 性能测试满足SLA要求

### 阶段4：监控和告警测试（1周）

#### 监控测试用例

1. Prometheus指标验证
  - 验证各微服务暴露/metrics端点
  - 验证指标数据格式正确
  - 验证指标包含关键业务指标
2. Grafana仪表板测试
  - 验证预定义仪表板存在
  - 验证仪表板数据正常显示
  - 验证仪表板刷新机制
3. 告警规则测试
  - 模拟高错误率触发告警
  - 验证告警通知渠道
  - 验证告警恢复机制

#### 关键测试场景

1. 完整用户工作流

用户上传图片 → Envoy网关路由 → OCR服务处理 → 返回文字识别结果
用户上传人脸 → 人脸服务注册 → 视频分析提交 → 异步处理 → 返回分析结果

2. 异步任务处理流程

视频提交 → 任务入队Redis → RQ工作进程处理 → 状态更新 → 结果存储 → 客户端轮询获取

3. 服务降级场景

人脸识别服务宕机 → OCR服务仍然可用 → 视频分析返回503 → 服务恢复后自动恢复

4. 性能基准测试

50个并发OCR请求 → 95%请求在1秒内响应 → 错误率低于2% → 资源使用在阈值内

### 测试数据管理策略

#### 静态测试数据

- 预先生成的测试图像和视频
- 预注册的人脸数据库
- 预期结果JSON文件

#### 动态测试数据

- 运行时生成的测试图像
- 从标准图像创建的测试视频
- 随机生成的不同语言文本

### 数据清理

- 测试结束后自动清理临时文件
- 重置数据库状态
- 清除Redis缓存

### 测试执行流程

# 1. 启动测试环境
docker-compose -f docker-compose.test.yml up -d

# 2. 等待服务就绪
python tests/utils/wait_for_services.py

# 3. 执行测试套件
pytest tests/unit/ -v --cov=app --cov-report=html
pytest tests/integration/ -v --tb=short
pytest tests/e2e/ -v --tb=short

# 4. 可选：性能测试
pytest tests/performance/ -v --tb=short -m performance

# 5. 生成综合报告
pytest tests/ --junitxml=test-results/junit.xml --html=test-results/report.html

# 6. 清理环境
docker-compose -f docker-compose.test.yml down -v

预期成果

量化指标

- 测试覆盖率从0%提升到80%以上
- 自动化测试执行时间控制在15分钟内
- 测试通过率95%以上
- 性能基准建立并定期验证

质量提升

- 早期发现集成问题
- 减少生产环境故障
- 提高部署信心
- 建立可重复的测试流程

运维支持

- 详细的测试报告和日志
- 性能趋势分析和预警
- 资源使用监控
- 故障场景重现能力

风险评估与缓解

风险1：测试环境与生产环境差异

- 缓解：使用相同的docker-compose模板，仅环境变量不同

风险2：测试执行时间过长

- 缓解：分层执行测试，并行运行独立测试用例

风险3：测试数据管理复杂

- 缓解：建立标准化的测试数据生成和清理工具

风险4：CI/CD流水线失败

- 缓解：设置分段执行，失败时保留现场环境用于调试

成功标准

1. 所有测试用例在CI/CD流水线中自动化执行
2. 测试覆盖率报告可在线查看
3. 性能基准测试定期执行并记录趋势
4. 监控告警测试验证通过
5. 团队接受新的测试流程和工具

后续演进

1. 添加混沌工程测试（服务随机故障注入）
2. 实施金丝雀部署测试
3. 建立A/B测试框架
4. 集成安全扫描（SAST/DAST）
5. 建立性能回归测试自动化

---
本计划基于对现有代码库的全面分析，结合微服务架构的最佳实践，旨在建立企业级的测试基础设施，确保AI服务微服务项目的质量和可靠性。
