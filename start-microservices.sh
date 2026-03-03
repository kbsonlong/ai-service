#!/bin/bash

# AI Service 微服务架构启动脚本
# 使用方法: ./start-microservices.sh [command]
#
# 命令:
#   up       启动所有服务
#   down     停止所有服务
#   logs     查看日志
#   status   查看服务状态
#   test     运行基本测试

set -e

# 配置
COMPOSE_FILE="docker-compose.microservices.yml"
PROJECT_NAME="ai-microservices"
ENVOY_PORT=8080
OCR_PORT=8001
FACE_PORT=8002
VIDEO_PORT=8003
REDIS_PORT=6379

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${BLUE}=== AI Service 微服务架构 ===${NC}"
    echo -e "${BLUE}============================${NC}"
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
    echo "启动微服务..."

    # 创建必要的目录
    mkdir -p face-service/data
    mkdir -p face-service/backups
    mkdir -p video-service/temp
    mkdir -p monitoring/grafana/provisioning

    # 启动服务
    docker-compose -f $COMPOSE_FILE -p $PROJECT_NAME up -d

    print_status "服务启动中..."
    echo -e "${YELLOW}等待服务就绪...${NC}"

    # 等待服务启动
    sleep 10

    # 检查服务状态
    check_services_health
}

stop_services() {
    print_header
    echo "停止微服务..."

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
    echo "服务状态:"

    docker-compose -f $COMPOSE_FILE -p $PROJECT_NAME ps

    echo -e "\n${BLUE}服务端点:${NC}"
    echo -e "  Envoy网关:    http://localhost:$ENVOY_PORT"
    echo -e "  OCR服务:      http://localhost:$OCR_PORT"
    echo -e "  人脸识别服务: http://localhost:$FACE_PORT"
    echo -e "  视频分析服务: http://localhost:$VIDEO_PORT"
    echo -e "  Redis:        localhost:$REDIS_PORT"
    echo -e "  Prometheus:   http://localhost:9090"
    echo -e "  Grafana:      http://localhost:3000 (admin/admin)"

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

    # 检查人脸识别服务
    if curl -s -f "http://localhost:$FACE_PORT/health" > /dev/null 2>&1; then
        print_status "人脸识别服务: 健康"
    else
        print_error "人脸识别服务: 不健康"
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
    echo "运行基本测试..."

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

    # 测试3: 检查OCR服务健康端点
    echo -e "\n${BLUE}测试3: 检查服务健康端点${NC}"
    if curl -s -f "http://localhost:$ENVOY_PORT/health" > /dev/null 2>&1; then
        print_status "健康检查端点正常"
    else
        print_error "健康检查端点异常"
        test_passed=false
    fi

    # 测试4: 检查各服务独立运行
    echo -e "\n${BLUE}测试4: 检查各服务独立运行${NC}"

    # OCR服务
    if curl -s -f "http://localhost:$OCR_PORT/health" > /dev/null 2>&1; then
        print_status "OCR服务独立运行正常"
    else
        print_error "OCR服务独立运行异常"
        test_passed=false
    fi

    # 人脸识别服务
    if curl -s -f "http://localhost:$FACE_PORT/health" > /dev/null 2>&1; then
        print_status "人脸识别服务独立运行正常"
    else
        print_error "人脸识别服务独立运行异常"
        test_passed=false
    fi

    # 视频分析服务
    if curl -s -f "http://localhost:$VIDEO_PORT/health" > /dev/null 2>&1; then
        print_status "视频分析服务独立运行正常"
    else
        print_error "视频分析服务独立运行异常"
        test_passed=false
    fi

    if [ "$test_passed" = true ]; then
        echo -e "\n${GREEN}所有测试通过！${NC}"
        echo -e "${GREEN}微服务架构运行正常。${NC}"
    else
        echo -e "\n${YELLOW}部分测试失败，请检查服务日志。${NC}"
    fi
}

cleanup() {
    print_header
    echo "清理临时文件..."

    # 停止服务
    docker-compose -f $COMPOSE_FILE -p $PROJECT_NAME down -v

    # 删除临时目录
    rm -rf face-service/data/* 2>/dev/null || true
    rm -rf video-service/temp/* 2>/dev/null || true

    print_status "清理完成"
}

show_help() {
    print_header
    echo "AI Service 微服务架构管理脚本"
    echo ""
    echo "使用方法: $0 [command]"
    echo ""
    echo "命令:"
    echo "  up       启动所有微服务"
    echo "  down     停止所有微服务"
    echo "  logs     查看服务日志"
    echo "  status   查看服务状态"
    echo "  test     运行基本功���测试"
    echo "  cleanup  清理所有服务和数据"
    echo "  help     显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0 up      # 启动所有服务"
    echo "  $0 status  # 查看服务状态"
    echo "  $0 test    # 运行测试"
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
        sleep 15  # 给服务更多时间启动
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