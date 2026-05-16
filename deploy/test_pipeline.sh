#!/bin/bash
set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCORING_URL="http://localhost:5000"
N8N_URL="http://localhost:5678"

echo "========================================="
echo "   求职自动化系统 - 端到端测试"
echo "========================================="
echo ""

echo -e "${YELLOW}[Step 1] 检查服务状态${NC}"
echo ""

echo ">>> 检查 Docker 容器..."
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "n8n|postgres" || {
  echo -e "${RED}Docker 容器未运行，请先执行: cd ~/job-automation/n8n && docker compose up -d${NC}"
  exit 1
}
echo ""

echo ">>> 检查评分服务..."
HEALTH=$(curl -s --connect-timeout 5 "$SCORING_URL/health" 2>/dev/null || echo '{"status":"unreachable"}')
if echo "$HEALTH" | grep -q '"ok"'; then
  echo -e "${GREEN}✅ 评分服务运行正常${NC}"
else
  echo -e "${RED}❌ 评分服务不可达 ($SCORING_URL)${NC}"
  echo "   请检查: sudo systemctl status scoring-service"
  exit 1
fi
echo ""

echo ">>> 检查 n8n..."
N8N_HEALTH=$(curl -s --connect-timeout 5 "$N8N_URL/healthz" 2>/dev/null || echo "unreachable")
if echo "$N8N_HEALTH" | grep -q "ok"; then
  echo -e "${GREEN}✅ n8n 运行正常${NC}"
else
  echo -e "${YELLOW}⚠️  n8n 可能还在启动中 ($N8N_URL)${NC}"
fi
echo ""

echo ">>> 检查数据库..."
docker exec job-postgres psql -U n8n -d job_automation -c "SELECT COUNT(*) as total_jobs FROM jobs;" 2>/dev/null && \
  echo -e "${GREEN}✅ 数据库连接正常${NC}" || \
  echo -e "${YELLOW}⚠️  数据库 job_automation.jobs 表尚未创建，请执行 init-db.sql${NC}"
echo ""

echo -e "${YELLOW}[Step 2] 测试评分服务${NC}"
echo ""

TEST_JD="我们正在寻找一名嵌入式Linux开发工程师：
1. 3年以上嵌入式Linux开发经验
2. 熟悉ARM架构和BSP开发
3. 精通C/C++语言
4. 有驱动开发经验优先
5. 熟悉Yocto/Buildroot构建系统
薪资范围：20-35K"

echo ">>> 发送测试 JD..."
RESULT=$(curl -s -X POST "$SCORING_URL/evaluate" \
  -H "Content-Type: application/json" \
  -d "$(printf '{"jd": "%s", "company": "测试科技", "role": "嵌入式Linux工程师"}' "$TEST_JD")" \
  --max-time 200 2>/dev/null || echo '{"error":"request failed"}')

echo ">>> 评分结果："
echo "$RESULT" | python3 -m json.tool 2>/dev/null || echo "$RESULT"
echo ""

SCORE=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('score',0))" 2>/dev/null || echo "0")
echo -e ">>> 评分: ${GREEN}${SCORE}/100${NC}"

if (( $(echo "$SCORE >= 80" | bc -l 2>/dev/null || echo 0) )); then
  echo -e "${GREEN}✅ 分数 >= 80，应该投递${NC}"
elif (( $(echo "$SCORE > 0" | bc -l 2>/dev/null || echo 0) )); then
  echo -e "${YELLOW}⚠️  分数 < 80，跳过投递${NC}"
else
  echo -e "${RED}❌ 评分失败，请检查 Gemini API Key 配置${NC}"
fi
echo ""

echo -e "${YELLOW}[Step 3] 测试 n8n 工作流${NC}"
echo ""
echo ">>> n8n 工作流需要在 n8n UI 中导入和激活"
echo "    1. 访问 $N8N_URL"
echo "    2. 导入 workflows/job-scraper-score.json"
echo "    3. 修改 Boss 直聘 Cookie 和钉钉 Token"
echo "    4. 激活工作流"
echo ""

echo "========================================="
echo -e "   ${GREEN}测试完成！${NC}"
echo "========================================="
