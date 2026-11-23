#!/usr/bin/env bash
# 企业 AI 知识库助手 - 一键启动脚本
# 用法：./start.sh [端口]，默认 8000
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${1:-8000}"

echo "[1/4] 检查 Python 依赖"
python -m pip install -q -r "$ROOT/backend/requirements.txt"

echo "[2/4] 检查前端构建产物"
if [ ! -f "$ROOT/frontend/dist/index.html" ]; then
  echo "  未发现 frontend/dist，开始构建前端"
  if [ ! -d "$ROOT/frontend/node_modules" ]; then
    (cd "$ROOT/frontend" && npm install)
  fi
  (cd "$ROOT/frontend" && npm run build)
else
  echo "  已存在构建产物，跳过构建"
fi

echo "[3/4] 初始化数据库（首次启动自动写入演示数据）"
mkdir -p "$ROOT/backend/data"

echo "[4/4] 启动服务：http://127.0.0.1:${PORT}"
cd "$ROOT/backend"
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
