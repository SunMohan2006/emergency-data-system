"""
应急数据清洗与可视化系统 - Flask 主程序
"""

import os
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file

from config import (
    UPLOAD_FOLDER,
    OUTPUT_FOLDER,
    LOG_FOLDER,
    ALLOWED_EXTENSIONS,
    MAX_FILE_SIZE,
)
from data_cleaner import clean_data

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE


# ==================== 工具函数 ====================

def allowed_file(filename: str) -> bool:
    """检查文件扩展名是否合法"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# ==================== 页面路由 ====================

@app.route('/')
def index():
    """系统首页：上传 + 可视化大屏"""
    return render_template('index.html')


# ==================== API 接口 ====================

@app.route('/api/upload', methods=['POST'])
def upload_and_clean():
    """
    上传 Excel 文件并执行智能清洗

    请求：multipart/form-data，字段名 file
    返回：JSON（清洗统计信息）
    """
    # 1. 检查是否有文件
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '未检测到上传文件，请选择文件后再提交'}), 400

    file = request.files['file']

    # 2. 检查是否选择了文件
    if file.filename == '':
        return jsonify({'success': False, 'message': '未选择文件，请重新选择'}), 400

    # 3. 检查文件格式
    if not allowed_file(file.filename):
        return jsonify({
            'success': False,
            'message': f'不支持的文件格式，仅支持: {", ".join(ALLOWED_EXTENSIONS)}'
        }), 400

    # 4. 保存上传文件
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    original_filename = f'{timestamp}_{file.filename}'
    upload_path = os.path.join(UPLOAD_FOLDER, original_filename)
    file.save(upload_path)

    # 5. 执行清洗
    try:
        result = clean_data(upload_path)
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'清洗过程出错: {str(e)}'
        }), 500

    # 6. 返回结果
    return jsonify({
        'success': True,
        'message': '数据清洗完成',
        'data': {
            'original_count': result['original_count'],
            'valid_count': result['valid_count'],
            'removed_dup_count': result['removed_dup_count'],
            'anomaly_count': result['anomaly_count'],
            'columns': result['columns'],
            'output_filename': os.path.basename(result['output_path']),
            'log_filename': os.path.basename(result['log_path']),
            'anomaly_logs': result['anomaly_logs'],
        }
    })


@app.route('/api/download/<filename>')
def download_file(filename):
    """
    下载清洗后的文件或日志文件

    参数：filename — 文件名（从 upload 接口的返回值中获取）
    """
    # 安全检查：防止路径穿越
    filename = os.path.basename(filename)

    # 优先在 outputs 中查找，找不到再去 logs
    for folder in [OUTPUT_FOLDER, LOG_FOLDER]:
        path = os.path.join(folder, filename)
        if os.path.exists(path):
            return send_file(
                path,
                as_attachment=True,
                download_name=filename,
            )

    return jsonify({'success': False, 'message': '文件不存在或已被清理'}), 404


@app.route('/api/health')
def health_check():
    """健康检查接口"""
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
    })


# ==================== 启动入口 ====================

if __name__ == '__main__':
    # 确保必要目录存在
    for folder in [UPLOAD_FOLDER, OUTPUT_FOLDER, LOG_FOLDER]:
        os.makedirs(folder, exist_ok=True)

    print('=' * 50)
    print('  应急数据清洗与可视化系统')
    print('  运行地址: http://127.0.0.1:5000')
    print('=' * 50)

    app.run(debug=True, host='127.0.0.1', port=5000)
