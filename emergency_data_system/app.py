"""
应急数据清洗与可视化系统 - Flask 主程序 v1.0
============================================
路由清单：
    GET  /                       系统首页（上传 + 可视化大屏）
    POST /api/upload             上传 Excel → 自动清洗 → 返回统计
    GET  /api/download/<file>    下载清洗结果 / 异常日志
    GET  /api/health             健康检查
    GET  /api/stats              全局数据统计
    GET  /api/history            历史清洗记录
    GET  /api/monthly            月度数据概览
    POST /auth/login             用户登录
    POST /auth/register          用户注册（管理员）
    POST /auth/logout            用户登出
    GET  /auth/status            登录状态查询
    GET  /auth/users             用户列表（管理员）
"""

import os
import uuid
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
from report import export_full_report
from database import init_db, CleanRecord, AnomalyRecord, close_session
from auth import init_auth, login_required, role_required

# ==================== Flask 初始化 ====================

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE

# 初始化认证模块（注册蓝图 + 设置 session 密钥）
init_auth(app)

# 初始化数据库（创建表结构）
init_db()


# ==================== 工具函数 ====================

def allowed_file(filename: str) -> bool:
    """检查文件扩展名是否在允许列表中"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def generate_batch_id() -> str:
    """生成唯一批次号"""
    return uuid.uuid4().hex[:12]


# ==================== 页面路由 ====================

@app.route('/')
def index():
    """系统首页：上传入口 + 可视化大屏"""
    return render_template('index.html')


# ==================== 核心 API ====================

@app.route('/api/upload', methods=['POST'])
def upload_and_clean():
    """
    上传 Excel 文件并执行全流程智能清洗

    请求格式:
        multipart/form-data, 字段名: file

    返回格式:
        {
            success: true/false,
            message: 状态描述,
            data: {
                original_count, valid_count, removed_dup_count,
                anomaly_count, columns, output_filename, log_filename,
                anomaly_logs: [{行号, 字段, 原始值, 异常类型, 处理方式}, ...],
                batch_id: 批次号
            }
        }
    """
    # ---- 校验 ----
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': '未检测到上传文件'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': '未选择文件'}), 400
    if not allowed_file(file.filename):
        return jsonify({
            'success': False,
            'message': f'不支持的文件格式，仅支持: {", ".join(ALLOWED_EXTENSIONS)}'
        }), 400

    # ---- 保存 ----
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    safe_filename = f'{timestamp}_{file.filename}'
    upload_path = os.path.join(UPLOAD_FOLDER, safe_filename)
    file.save(upload_path)

    # ---- 清洗 ----
    batch_id = generate_batch_id()
    try:
        result = clean_data(upload_path)
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'清洗过程出错: {str(e)}'
        }), 500

    # ---- 生成增强报表 ----
    enhanced_output_filename = f'完整报表_{timestamp}.xlsx'
    enhanced_output_path = os.path.join(OUTPUT_FOLDER, enhanced_output_filename)
    try:
        import pandas as pd
        data_df = pd.read_excel(result['output_path'])
        export_full_report(
            data_df,
            result['anomaly_logs'],
            {
                'original_count': result['original_count'],
                'valid_count': result['valid_count'],
                'removed_dup_count': result['removed_dup_count'],
                'anomaly_count': result['anomaly_count'],
            },
            enhanced_output_path,
            file.filename,
        )
    except Exception:
        # 增强报表生成失败不影响主流程
        enhanced_output_filename = result['output_filename']

    # ---- 持久化到数据库 ----
    try:
        clean_records = []
        for _, row in pd.read_excel(result['output_path']).iterrows():
            clean_records.append({
                'batch_id': batch_id,
                'company_name': str(row.get('企业名称', '')),
                'phone': str(row.get('联系电话', '')),
                'check_date': str(row.get('排查日期', '')),
                'address': str(row.get('企业地址', '')),
                'check_type': str(row.get('排查类型', '')),
                'source_file': file.filename,
                'is_anomaly': str(row.get('企业名称', '')) == '待补充' or str(row.get('联系电话', '')) == '待补充',
            })
        CleanRecord.save_batch(clean_records)
        AnomalyRecord.save_batch(result['anomaly_logs'], batch_id)
    except Exception:
        pass  # 数据库写入失败不影响主流程

    # ---- 返回 ----
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
            'enhanced_filename': enhanced_output_filename,
            'batch_id': batch_id,
            'anomaly_logs': result['anomaly_logs'],
        }
    })


@app.route('/api/download/<filename>')
def download_file(filename: str):
    """
    下载文件（清洗结果 / 异常日志 / 增强报表）

    安全措施: 使用 os.path.basename 防止路径穿越攻击
    """
    filename = os.path.basename(filename)
    for folder in [OUTPUT_FOLDER, LOG_FOLDER]:
        path = os.path.join(folder, filename)
        if os.path.exists(path):
            return send_file(path, as_attachment=True, download_name=filename)

    return jsonify({'success': False, 'message': '文件不存在或已被清理'}), 404


# ==================== 数据统计 API ====================

@app.route('/api/stats')
def get_stats():
    """获取全局数据统计（用于可视化大屏）"""
    try:
        db_stats = CleanRecord.get_stats()
        return jsonify({'success': True, 'data': db_stats})
    except Exception:
        return jsonify({'success': True, 'data': {
            'total_records': 0, 'anomaly_records': 0,
            'total_batches': 0, 'anomaly_rate': '0%',
        }})


@app.route('/api/history')
def get_history():
    """获取历史清洗记录列表（最近20个批次）"""
    try:
        records = CleanRecord.query_all(limit=200)

        # 按批次号聚合
        batches = {}
        for r in records:
            bid = r.get('batch_id', '')
            if bid not in batches:
                batches[bid] = {
                    'batch_id': bid,
                    'source_file': r.get('source_file', ''),
                    'total': 0,
                    'anomaly': 0,
                    'created_at': r.get('created_at', ''),
                }
            batches[bid]['total'] += 1
            if r.get('is_anomaly'):
                batches[bid]['anomaly'] += 1

        batch_list = sorted(
            batches.values(),
            key=lambda b: b.get('created_at', ''),
            reverse=True,
        )[:20]

        return jsonify({'success': True, 'data': batch_list})
    except Exception:
        return jsonify({'success': True, 'data': []})


@app.route('/api/monthly')
def get_monthly():
    """获取月度数据统计"""
    try:
        monthly = CleanRecord.get_monthly_stats()
        return jsonify({'success': True, 'data': monthly})
    except Exception:
        return jsonify({'success': True, 'data': []})


@app.route('/api/health')
def health_check():
    """健康检查"""
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
    })


# ==================== 管理 API（需登录） ====================

@app.route('/api/admin/cleanup', methods=['POST'])
@login_required
@role_required('admin')
def cleanup_old_data():
    """清理指定批次的旧数据（仅管理员）"""
    data = request.get_json(silent=True) or {}
    batch_id = data.get('batch_id', '')

    if not batch_id:
        return jsonify({'success': False, 'message': '请指定批次号'}), 400

    try:
        count = CleanRecord.delete_by_batch(batch_id)
        return jsonify({
            'success': True,
            'message': f'已清理 {count} 条记录',
        })
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


# ==================== 应用上下文清理 ====================

@app.teardown_appcontext
def shutdown_session(exception=None):
    """请求结束后关闭数据库会话"""
    close_session()


# ==================== 启动入口 ====================

if __name__ == '__main__':
    for folder in [UPLOAD_FOLDER, OUTPUT_FOLDER, LOG_FOLDER]:
        os.makedirs(folder, exist_ok=True)

    print('=' * 50)
    print('  应急数据清洗与可视化系统  v1.0')
    print('  运行地址: http://127.0.0.1:5000')
    print('  默认管理员: admin / admin123')
    print('=' * 50)

    app.run(debug=True, host='127.0.0.1', port=5000)
