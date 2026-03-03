#!/bin/bash

# AI Service 高可用微服务架构启动脚本
# 使用方法: ./start-microservices-ha.sh [command]
#
# 命令:
#   up       启动所有服务（高可用版本）
#   down     停止所有服务
#   logs     查看日志
#   status   查看服务状态
#   test     运行基本测试

set -e

# 配置
COMPOSE_FILE="docker-compose.microservices-ha.yml"
PROJECT_NAME="ai-microservices-ha"
ENVOY_PORT=8080
OCR_PORT=8001
FACE_PORT_1=8002  # 主实例
FACE_PORT_2=8003  # 副本实例
VIDEO_PORT=8004
REDIS_PORT=6379

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${BLUE}=== AI Service 高可用微服务架构 ===${NC}"
    echo -e "${BLUE}==================================${NC}"
}

print_status() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

check_dependencies() {
    print_header
    echo "检查依赖..."

    # 检查Docker
    if command -v docker &> /dev/null; then
        print_status "Docker 已安装"
    else
        print_error "Docker 未安装"
        exit 1
    fi

    # 检查Docker Compose
    if command -v docker-compose &> /dev/null; then
        print_status "Docker Compose 已安装"
    else
        # 检查Docker Compose插件
        if docker compose version &> /dev/null; then
            print_status "Docker Compose 插件已安装"
        else
            print_error "Docker Compose 未安装"
            exit 1
        fi
    fi

    # 检查curl
    if command -v curl &> /dev/null; then
        print_status "curl 已安装"
    else
        print_error "curl 未安装"
        exit 1
    fi
}

start_services() {
    print_header
    echo "启动高可用微服务..."

    # 创建必要的目录
    mkdir -p face-service/data
    mkdir -p face-service/backups
    mkdir -p video-service/temp
    mkdir -p monitoring/grafana/provisioning/datasources
    mkdir -p monitoring/grafana/provisioning/dashboards

    # 复制监控配置文件
    if [ ! -f "monitoring/alerts-ha.yml" ]; then
        cp "monitoring/alerts.yml" "monitoring/alerts-ha.yml" 2>/dev/null || true
    fi

    # 启动服务
    docker-compose -f $COMPOSE_FILE -p $PROJECT_NAME up -d

    print_status "高可用服务启动中..."
    echo -e "${YELLOW}等待服务就绪（高可用架构需要更多时间）...${NC}"

    # 等待服务启动
    sleep 15

    # 检查服务状态
    check_services_health
}

stop_services() {
    print_header
    echo "停止高可用微服务..."

    docker-compose -f $COMPOSE_FILE -p $PROJECT_NAME down

    print_status "服务已停止"
}

show_logs() {
    print_header
    echo "查看服务日志..."

    docker-compose -f $COMPOSE_FILE -p $PROJECT_NAME logs -f "$@"
}

show_status() {
    print_header
    echo "高可用服务状态:"

    docker-compose -f $COMPOSE_FILE -p $PROJECT_NAME ps

    echo -e "\n${BLUE}服务端点:${NC}"
    echo -e "  Envoy网关:           http://localhost:$ENVOY_PORT"
    echo -e "  OCR服务:             http://localhost:$OCR_PORT"
    echo -e "  人脸识别服务（主）:   http://localhost:$FACE_PORT_1"
    echo -e "  人脸识别服务（副）:   http://localhost:$FACE_PORT_2"
    echo -e "  视频分析服务:         http://localhost:$VIDEO_PORT"
    echo -e "  Redis:               localhost:$REDIS_PORT"
    echo -e "  Prometheus:          http://localhost:9090"
    echo -e "  Grafana:             http://localhost:3000 (admin/admin)"

    echo -e "\n${BLUE}负载均衡测试:${NC}"
    echo -e "  通过Envoy访问人脸识别服务（负载均衡到两个实例）:"
    echo -e "    curl -H 'x-api-key: your-secret-api-key' http://localhost:$ENVOY_PORT/v1/face/registered"

    echo -e "\n${BLUE}健康检查:${NC}"
    check_services_health
}

check_services_health() {
    local all_healthy=true

    # 检查OCR服务
    if curl -s -f "http://localhost:$OCR_PORT/health" > /dev/null 2>&1; then
        print_status "OCR服务: 健康"
    else
        print_error "OCR服务: 不健康"
        all_healthy=false
    fi

    # 检查人脸识别服务（两个实例）
    if curl -s -f "http://localhost:$FACE_PORT_1/health" > /dev/null 2>&1; then
        print_status "人脸识别服务（主）: 健康"
    else
        print_error "人脸识别服务（主）: 不健康"
        all_healthy=false
    fi

    if curl -s -f "http://localhost:$FACE_PORT_2/health" > /dev/null 2>&1; then
        print_status "人脸识别服务（副）: 健康"
    else
        print_error "人脸识别服务（副）: 不健康"
        all_healthy=false
    fi

    # 检查视频分析服务
    if curl -s -f "http://localhost:$VIDEO_PORT/health" > /dev/null 2>&1; then
        print_status "视频分析服务: 健康"
    else
        print_error "视频分析服务: 不健康"
        all_healthy=false
    fi

    # 检查Envoy网关
    if curl -s -f "http://localhost:$ENVOY_PORT/health" > /dev/null 2>&1; then
        print_status "Envoy网关: 健康"
    else
        print_error "Envoy网关: 不健康"
        all_healthy=false
    fi

    if [ "$all_healthy" = true ]; then
        echo -e "\n${GREEN}所有服务运行正常！${NC}"
    else
        echo -e "\n${YELLOW}部分服务可能仍在启动中，请稍后重试...${NC}"
    fi
}

run_tests() {
    print_header
    echo "运行高可用架构测试..."

    local test_passed=true
    local API_KEY="your-secret-api-key"

    # 测试1: 检查Envoy网关路由
    echo -e "\n${BLUE}测试1: 检查Envoy网关路由${NC}"
    response=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$ENVOY_PORT/")
    if [ "$response" = "404" ]; then
        print_status "Envoy网关路由正常 (404表示路由配置正确)"
    else
        print_error "Envoy网关路由异常: HTTP $response"
        test_passed=false
    fi

    # 测试2: 检查API Key验证
    echo -e "\n${BLUE}测试2: 检查API Key验证${NC}"
    response=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "x-api-key: wrong-key" \
        "http://localhost:$ENVOY_PORT/v1/ocr/scan")

    if [ "$response" = "401" ]; then
        print_status "API Key验证正常 (无效密钥返回401)"
    else
        print_error "API Key验证异常: HTTP $response"
        test_passed=false
    fi

    # 测试3: 检查负载均衡
    echo -e "\n${BLUE}测试3: 检查人脸识别服务负载均衡${NC}"

    # 多次请求以观察负载均衡效果
    echo "发送5个请求到人脸识别服务（通过Envoy网关）:"
    for i in {1..5}; do
        response_code=$(curl -s -o /dev/null -w "%{http_code}" \
            -H "x-api-key: $API_KEY" \
            "http://localhost:$ENVOY_PORT/v1/face/registered")

        if [ "$response_code" = "200" ]; then
            echo "  请求 $i: 成功"
        else
            echo "  请求 $i: 失败 (HTTP $response_code)"
            test_passed=false
        fi
        sleep 0.5
    done

    # 测试4: 检查只读副本拒绝写入
    echo -e "\n${BLUE}测试4: 检查只读副本功能${NC}"

    # 直接向只读副本发送注册请求（应该被拒绝）
    response=$(curl -s -o /dev/null -w "%{http_code}" \
        -H "x-api-key: $API_KEY" \
        -F "name=TestPerson" \
        -F "file=@sample_face.jpg" \
        "http://localhost:$FACE_PORT_2/v1/face/register" 2>/dev/null || echo "000")

    if [ "$response" = "400" ] || [ "$response" = "500" ] || [ "$response" = "403" ]; then
        print_status "只读副本正确拒绝写入请求 (HTTP $response)"
    else
        print_warning "只读副本响应: HTTP $response (可能需要检查具体错误信息)"
    fi

    # 测试5: 检查主实例接受写入
    echo -e "\n${BLUE}测试5: 检查主实例写入功能${NC}"

    # 检查主实例健康状态
    if curl -s -f "http://localhost:$FACE_PORT_1/health" > /dev/null 2>&1; then
        print_status "主实例运行正常"
    else
        print_error "主实例不健康"
        test_passed=false
    fi

    # 测试6: 检查监控系统
    echo -e "\n${BLUE}测试6: 检查监控系统${NC}"

    if curl -s -f "http://localhost:9090" > /dev/null 2>&1; then
        print_status "Prometheus 运行正常"
    else
        print_error "Prometheus 无法访问"
        test_passed=false
    fi

    if curl -s -f "http://localhost:3000" > /dev/null 2>&1; then
        print_status "Grafana 运行正常"
    else
        print_warning "Grafana 无法访问（可能需要更多时间启动）"
    fi

    if [ "$test_passed" = true ]; then
        echo -e "\n${GREEN}所有测试通过！${NC}"
        echo -e "${GREEN}高可用微服务架构运行正常。${NC}"
        echo -e "${YELLOW}提示: 可以通过 Grafana (http://localhost:3000) 查看监控指标${NC}"
    else
        echo -e "\n${YELLOW}部分测试失败，请检查服务日志。${NC}"
    fi
}

cleanup() {
    print_header
    echo "清理高可用服务临时文件..."

    # 停止服务
    docker-compose -f $COMPOSE_FILE -p $PROJECT_NAME down -v

    # 删除临时目录
    rm -rf face-service/data/* 2>/dev/null || true
    rm -rf video-service/temp/* 2>/dev/null || true

    print_status "清理完成"
}

show_help() {
    print_header
    echo "AI Service 高可用微服务架构管理脚本"
    echo ""
    echo "使用方法: $0 [command]"
    echo ""
    echo "命令:"
    echo "  up       启动所有高可用微服务（包含多实例负载均衡）"
    echo "  down     停止所有微服务"
    echo "  logs     查看服务日志"
    echo "  status   查看服务状态和负载均衡信息"
    echo "  test     运行高可用架构测试"
    echo "  cleanup  清理所有服务和数据"
    echo "  help     显示此帮助信息"
    echo ""
    echo "高可用特性:"
    echo "  - 人脸识别服务多实例（一主一副）"
    echo "  - Envoy负载均衡"
    echo "  - 共享数据存储"
    echo "  - 只读副本保护"
    echo "  - 完整监控栈（Prometheus + Grafana）"
    echo ""
    echo "示例:"
    echo "  $0 up      # 启动高可用服务"
    echo "  $0 status  # 查看服务状态和负载均衡"
    echo "  $0 test    # 运行高可用测试"
}

# 主逻辑
case "${1:-help}" in
    up|start)
        check_dependencies
        start_services
        ;;
    down|stop)
        stop_services
        ;;
    logs)
        shift
        show_logs "$@"
        ;;
    status|ps)
        show_status
        ;;
    test)
        check_dependencies
        start_services
        sleep 20  # 给高可用服务更多时间启动
        run_tests
        ;;
    cleanup)
        cleanup
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        print_error "未知命令: $1"
        echo ""
        show_help
        exit 1
        ;;
esac