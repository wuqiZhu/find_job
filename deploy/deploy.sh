#!/bin/bash
set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}"
echo "╔═══════════════════════════════════════════╗"
echo "║   自动化求职助手系统 - 一键部署脚本        ║"
echo "╚═══════════════════════════════════════════╝"
echo -e "${NC}"

DEPLOY_DIR="/opt/job-automation"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo -e "${YELLOW}[1/6] 检查系统环境${NC}"
echo ""

if ! command -v docker &> /dev/null; then
  echo -e "${YELLOW}Docker 未安装，正在安装...${NC}"
  curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
  sudo sh /tmp/get-docker.sh
  sudo usermod -aG docker $USER
  echo -e "${GREEN}Docker 安装完成${NC}"
else
  echo -e "${GREEN}✅ Docker 已安装: $(docker --version)${NC}"
fi

if ! command -v docker compose &> /dev/null; then
  echo -e "${YELLOW}Docker Compose 未安装，正在安装...${NC}"
  sudo apt install docker-compose-plugin -y
else
  echo -e "${GREEN}✅ Docker Compose 已安装${NC}"
fi

if ! command -v node &> /dev/null; then
  echo -e "${YELLOW}Node.js 未安装，正在安装...${NC}"
  curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
  sudo apt install -y nodejs
else
  echo -e "${GREEN}✅ Node.js 已安装: $(node --version)${NC}"
fi

if ! command -v python3 &> /dev/null; then
  echo -e "${YELLOW}Python3 未安装，正在安装...${NC}"
  sudo apt install -y python3 python3-pip python3-venv
else
  echo -e "${GREEN}✅ Python3 已安装: $(python3 --version)${NC}"
fi
echo ""

echo -e "${YELLOW}[2/6] 创建目录结构${NC}"
echo ""
sudo mkdir -p "$DEPLOY_DIR"/{n8n,career-ops,scoring-service,data}
sudo cp -r "$SCRIPT_DIR/n8n/"* "$DEPLOY_DIR/n8n/"
sudo cp -r "$SCRIPT_DIR/scoring-service/"* "$DEPLOY_DIR/scoring-service/"
echo -e "${GREEN}✅ 目录结构创建完成${NC}"
echo ""

echo -e "${YELLOW}[3/6] 部署 n8n + PostgreSQL${NC}"
echo ""
cd "$DEPLOY_DIR/n8n"
echo ">>> 启动 n8n 和 PostgreSQL..."
sudo docker compose up -d
echo ">>> 等待服务启动..."
sleep 10
echo -e "${GREEN}✅ n8n + PostgreSQL 部署完成${NC}"
echo "   n8n 访问地址: http://$(hostname -I | awk '{print $1}'):5678"
echo ""

echo -e "${YELLOW}[4/6] 部署 career-ops 评分服务${NC}"
echo ""
if [ ! -d "$DEPLOY_DIR/career-ops/node_modules" ]; then
  echo ">>> 克隆 career-ops..."
  cd "$DEPLOY_DIR/career-ops"
  git clone https://github.com/santifer/career-ops.git . 2>/dev/null || true
  echo ">>> 安装依赖..."
  npm install
  npx playwright install chromium --with-deps
else
  echo ">>> career-ops 已存在，跳过克隆"
fi

echo ">>> 创建 Python 虚拟环境..."
cd "$DEPLOY_DIR/scoring-service"
python3 -m venv venv
./venv/bin/pip install -r requirements.txt

echo ">>> 配置 systemd 服务..."
sudo cp "$DEPLOY_DIR/scoring-service/scoring-service.service" /etc/systemd/system/
sudo sed -i "s|CAREER_OPS_DIR=.*|CAREER_OPS_DIR=$DEPLOY_DIR/career-ops|g" /etc/systemd/system/scoring-service.service
sudo sed -i "s|WorkingDirectory=.*|WorkingDirectory=$DEPLOY_DIR/scoring-service|g" /etc/systemd/system/scoring-service.service
sudo sed -i "s|ExecStart=.*|ExecStart=$DEPLOY_DIR/scoring-service/venv/bin/gunicorn -w 2 -b 0.0.0.0:5000 --timeout 300 app:app|g" /etc/systemd/system/scoring-service.service
sudo systemctl daemon-reload
sudo systemctl enable scoring-service
sudo systemctl start scoring-service
echo -e "${GREEN}✅ 评分服务部署完成${NC}"
echo "   评分服务地址: http://$(hostname -I | awk '{print $1}'):5000"
echo ""

echo -e "${YELLOW}[5/7] 等待服务就绪${NC}"
echo ""
echo ">>> 等待 n8n 就绪..."
for i in $(seq 1 30); do
  if curl -s http://localhost:5678/healthz >/dev/null 2>&1; then
    echo -e "${GREEN}✅ n8n 已就绪${NC}"
    break
  fi
  sleep 2
done

echo ">>> 等待评分服务就绪..."
for i in $(seq 1 15); do
  if curl -s http://localhost:5000/health >/dev/null 2>&1; then
    echo -e "${GREEN}✅ 评分服务已就绪${NC}"
    break
  fi
  sleep 2
done
echo ""

echo -e "${YELLOW}[6/7] 检查数据库${NC}"
echo ""
docker exec job-postgres psql -U n8n -d job_automation -c "SELECT COUNT(*) FROM jobs;" >/dev/null 2>&1 && \
  echo -e "${GREEN}✅ 数据库 job_automation.jobs 表存在${NC}" || \
  echo -e "${YELLOW}⚠️  请手动执行初始化 SQL: docker exec -i job-postgres psql -U n8n -d job_automation < $DEPLOY_DIR/n8n/init-db.sql${NC}"
echo ""

echo -e "${YELLOW}[7/7] 输出配置信息${NC}"
echo ""
SERVER_IP=$(hostname -I | awk '{print $1}')
echo -e "${CYAN}╔═══════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║         部署完成！以下是配置信息           ║${NC}"
echo -e "${CYAN}╠═══════════════════════════════════════════╣${NC}"
echo -e "${CYAN}║${NC} n8n 地址:     http://${SERVER_IP}:5678       ${CYAN}║${NC}"
echo -e "${CYAN}║${NC} 评分服务:     http://${SERVER_IP}:5000       ${CYAN}║${NC}"
echo -e "${CYAN}║${NC} PostgreSQL:   ${SERVER_IP}:5433              ${CYAN}║${NC}"
echo -e "${CYAN}╠═══════════════════════════════════════════╣${NC}"
echo -e "${CYAN}║${NC} 接下来你需要:                             ${CYAN}║${NC}"
echo -e "${CYAN}║${NC} 1. 访问 n8n 创建管理员账号                ${CYAN}║${NC}"
echo -e "${CYAN}║${NC} 2. 导入工作流 workflows/*.json            ${CYAN}║${NC}"
echo -e "${CYAN}║${NC} 3. 配置 Boss 直聘 Cookie                  ${CYAN}║${NC}"
echo -e "${CYAN}║${NC} 4. 配置 MIMO_API_KEY                      ${CYAN}║${NC}"
echo -e "${CYAN}║${NC} 5. 配置钉钉 Webhook Token                ${CYAN}║${NC}"
echo -e "${CYAN}╚═══════════════════════════════════════════╝${NC}"
echo ""
echo -e "运行测试: bash $DEPLOY_DIR/test_pipeline.sh"
