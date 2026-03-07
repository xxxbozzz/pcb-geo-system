#!/bin/bash
# ═══════════════════════════════════════════════════════
#  PCB GEO 知识引擎 — 阿里云部署脚本 v3.0
#  用法: ./deploy.sh <服务器IP>
#  示例: ./deploy.sh 47.76.50.157
# ═══════════════════════════════════════════════════════

SERVER_IP=$1
USER="root"
REMOTE_DIR="/opt/pcb-geo-system"

if [ -z "$SERVER_IP" ]; then
    echo "❌ 用法: ./deploy.sh <服务器IP>"
    exit 1
fi

GIT_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo "unknown")
GIT_COMMIT_SHORT=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
GIT_BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "unknown")
if [ -n "$(git status --porcelain --untracked-files=all 2>/dev/null)" ]; then
    GIT_DIRTY=true
else
    GIT_DIRTY=false
fi
DEPLOYED_AT=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
TMP_BUILD_INFO=$(mktemp /tmp/pcb-geo-build.XXXXXX.json)
trap 'rm -f "$TMP_BUILD_INFO"' EXIT

cat > "$TMP_BUILD_INFO" <<EOF
{
  "git_commit": "$GIT_COMMIT",
  "git_commit_short": "$GIT_COMMIT_SHORT",
  "git_branch": "$GIT_BRANCH",
  "git_dirty": $GIT_DIRTY,
  "deployed_at": "$DEPLOYED_AT"
}
EOF

echo "🚀 PCB GEO v3.0 部署到 $SERVER_IP"
echo "🧾 部署版本: $GIT_BRANCH@$GIT_COMMIT_SHORT (dirty=$GIT_DIRTY)"

# ─── 1. 远程环境准备 ───
echo "📦 准备远程环境..."
ssh $USER@$SERVER_IP << 'SETUP'
    # Docker 安装检查
    if ! command -v docker &> /dev/null; then
        echo "安装 Docker..."
        curl -fsSL https://get.docker.com | sh
        systemctl enable docker && systemctl start docker
    fi
    if ! docker compose version &> /dev/null; then
        echo "安装 Docker Compose..."
        apt-get update && apt-get install -y docker-compose-plugin
    fi
    mkdir -p /opt/pcb-geo-system
    echo "✅ 环境就绪"
SETUP

# ─── 2. 同步代码 ───
echo "📤 同步代码..."
rsync -avz --progress \
    --exclude '.git' --exclude 'venv' --exclude '__pycache__' \
    --exclude '*.log' --exclude '.DS_Store' --exclude 'database/mysql_data' \
    --exclude 'database/chroma_data' --exclude 'node_modules' \
    ./ $USER@$SERVER_IP:$REMOTE_DIR/

rsync -avz "$TMP_BUILD_INFO" "$USER@$SERVER_IP:$REMOTE_DIR/build_info.json"

# ─── 3. 远程构建 & 启动 ───
echo "🐳 构建并启动容器..."
ssh $USER@$SERVER_IP << 'DEPLOY'
    cd /opt/pcb-geo-system

    # 清理旧构建缓存（防止 snapshot 损坏）
    docker compose down 2>/dev/null
    docker builder prune -f 2>/dev/null
    docker system prune -f 2>/dev/null

    # 构建并启动
    docker compose up -d --build --force-recreate

    # 等待 MySQL 就绪
    echo "⏳ 等待 MySQL..."
    sleep 10
    for i in $(seq 1 30); do
        if docker exec geo-mysql mysqladmin ping -h localhost -u root -proot_password 2>/dev/null | grep -q alive; then
            echo "✅ MySQL 就绪"
            break
        fi
        sleep 2
    done

    # 初始化数据库表
    docker exec geo-agent-core python scripts/init_mysql.py 2>&1 || echo "⚠️ init_mysql 失败（可能已初始化）"

    # 导入种子话题
    docker exec geo-agent-core python scripts/load_seed_topics.py 2>&1 || echo "⚠️ 种子导入跳过"

    # 检查容器状态
    echo ""
    echo "📊 容器状态:"
    docker ps --format 'table {{.Names}}\t{{.Status}}'

    echo ""
    echo "═══════════════════════════════════"
    echo "  ✅ 部署完成!"
    echo "  Dashboard: http://$(curl -s ifconfig.me 2>/dev/null || echo $HOSTNAME):8503"
    echo "═══════════════════════════════════"
DEPLOY

echo "🎉 部署完成! Dashboard: http://$SERVER_IP:8503"
