# ============================================================================
#  应急数据清洗与可视化系统 — Docker 镜像
# ============================================================================
#  构建: docker build -t emergency-data-system .
#  运行: docker run -p 5000:5000 emergency-data-system
# ============================================================================

FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖（openpyxl 需要 libxlsxwriter 等，slim 镜像已包含基础库）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 先复制依赖文件（利用 Docker 层缓存，依赖没变就不重新 pip install）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 复制源码
COPY . .

# 创建运行时目录
RUN mkdir -p uploads outputs logs

# 暴露端口
EXPOSE 5000

# 生产模式：用 Waitress 替代 Flask 内置服务器
# Waitress 是纯 Python WSGI 服务器，无需额外系统依赖
RUN pip install --no-cache-dir waitress -i https://pypi.tuna.tsinghua.edu.cn/simple

# 启动命令
CMD ["python", "-c", "from waitress import serve; from app import app; print('应急数据清洗系统已启动 → http://0.0.0.0:5000'); serve(app, host='0.0.0.0', port=5000)"]
