"""
用户认证模块
基于 Flask session + werkzeug 密码哈希，提供登录/注册/登出/会话管理

设计原则：
    1. 零外部依赖 —— 仅使用 Flask 内置 session 和 werkzeug.security
    2. 安全基线 —— 密码哈希存储（SHA256 + salt），杜绝明文
    3. 最小权限 —— 默认两个角色：admin（管理员）和 operator（操作员）
    4. 无状态会话 —— 基于 Flask signed cookie，无需 Redis/数据库存储会话

使用方式：
    from auth import init_auth, login_required, role_required
    init_auth(app)                  # 注册认证模块
    @login_required                 # 保护路由：需要登录
    @role_required('admin')         # 保护路由：需要管理员角色
"""

import os
import json
import functools
from typing import Optional, Dict, Any, List

from flask import session, redirect, url_for, flash, request, jsonify, Blueprint
from werkzeug.security import generate_password_hash, check_password_hash

# ==================== 认证蓝图 ====================

auth_bp = Blueprint('auth', __name__, url_prefix='/auth')

# ==================== 用户存储 ====================

# 用户数据文件路径（本地 JSON，避免额外依赖数据库）
USERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'users.json')

# 默认管理员账户（首次启动自动创建）
DEFAULT_ADMIN = {
    'username': 'admin',
    'password': generate_password_hash('admin123'),  # 首次登录后建议修改
    'role': 'admin',
    'display_name': '系统管理员',
}


def _load_users() -> Dict[str, Dict[str, str]]:
    """从本地 JSON 文件加载用户数据"""
    if not os.path.exists(USERS_FILE):
        _save_users({'admin': DEFAULT_ADMIN})
        return {'admin': DEFAULT_ADMIN}

    with open(USERS_FILE, 'r', encoding='utf-8') as f:
        users = json.load(f)
    # 确保默认管理员始终存在
    if 'admin' not in users:
        users['admin'] = DEFAULT_ADMIN
        _save_users(users)
    return users


def _save_users(users: Dict[str, Dict[str, str]]) -> None:
    """持久化用户数据到本地 JSON 文件"""
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, ensure_ascii=False, indent=2)


def _get_user(username: str) -> Optional[Dict[str, str]]:
    """按用户名查找用户，返回用户字典或 None"""
    users = _load_users()
    return users.get(username)


# ==================== 认证路由 ====================

@auth_bp.route('/login', methods=['POST'])
def login():
    """
    用户登录接口

    请求体（JSON）:
        username: 用户名
        password: 密码

    成功返回 200 + 用户信息
    失败返回 401
    """
    data = request.get_json(silent=True) or {}

    username = (data.get('username') or '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({'success': False, 'message': '用户名和密码不能为空'}), 400

    user = _get_user(username)
    if user is None:
        return jsonify({'success': False, 'message': '用户名或密码错误'}), 401

    if not check_password_hash(user['password'], password):
        return jsonify({'success': False, 'message': '用户名或密码错误'}), 401

    # 登录成功：写入 session
    session['user'] = {
        'username': username,
        'role': user['role'],
        'display_name': user.get('display_name', username),
    }
    session.permanent = True  # 持久化会话（浏览器关闭后仍有效）

    return jsonify({
        'success': True,
        'message': f'欢迎回来，{user.get("display_name", username)}',
        'data': {
            'username': username,
            'role': user['role'],
            'display_name': user.get('display_name', username),
        }
    })


@auth_bp.route('/register', methods=['POST'])
def register():
    """
    用户注册接口（仅管理员可操作）

    请求体（JSON）:
        username: 新用户名
        password: 密码
        role: 角色（operator/admin，默认为 operator）
        display_name: 显示名称
    """
    # 检查当前用户是否是管理员
    current_user = session.get('user', {})
    if current_user.get('role') != 'admin':
        return jsonify({'success': False, 'message': '仅管理员可创建新用户'}), 403

    data = request.get_json(silent=True) or {}
    username = (data.get('username') or '').strip()
    password = data.get('password', '')

    if not username or len(username) < 2:
        return jsonify({'success': False, 'message': '用户名至少2个字符'}), 400
    if not password or len(password) < 6:
        return jsonify({'success': False, 'message': '密码至少6个字符'}), 400

    users = _load_users()
    if username in users:
        return jsonify({'success': False, 'message': '用户名已存在'}), 409

    users[username] = {
        'username': username,
        'password': generate_password_hash(password),
        'role': data.get('role', 'operator'),
        'display_name': data.get('display_name', username),
    }
    _save_users(users)

    return jsonify({
        'success': True,
        'message': f'用户 {username} 创建成功',
    })


@auth_bp.route('/logout', methods=['POST'])
def logout():
    """用户登出：清除会话"""
    session.pop('user', None)
    return jsonify({'success': True, 'message': '已安全退出'})


@auth_bp.route('/status', methods=['GET'])
def status():
    """查询当前登录状态"""
    user = session.get('user')
    if user:
        return jsonify({
            'success': True,
            'logged_in': True,
            'data': {
                'username': user['username'],
                'role': user['role'],
                'display_name': user.get('display_name', ''),
            }
        })
    return jsonify({'success': True, 'logged_in': False})


@auth_bp.route('/users', methods=['GET'])
def list_users():
    """列出所有用户（仅管理员）"""
    current_user = session.get('user', {})
    if current_user.get('role') != 'admin':
        return jsonify({'success': False, 'message': '权限不足'}), 403

    users = _load_users()
    user_list = [
        {
            'username': u['username'],
            'role': u['role'],
            'display_name': u.get('display_name', ''),
        }
        for u in users.values()
    ]
    return jsonify({'success': True, 'data': user_list})


# ==================== 装饰器 ====================

def login_required(f):
    """
    路由保护装饰器：未登录用户返回 401

    用法:
        @app.route('/protected')
        @login_required
        def protected():
            ...
    """
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            # API 请求返回 JSON，页面请求重定向
            if request.path.startswith('/api/') or request.path.startswith('/auth/'):
                return jsonify({'success': False, 'message': '请先登录'}), 401
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated


def role_required(role: str):
    """
    角色限制装饰器：非指定角色返回 403

    用法:
        @app.route('/admin')
        @login_required
        @role_required('admin')
        def admin():
            ...
    """
    def decorator(f):
        @functools.wraps(f)
        def decorated(*args, **kwargs):
            user = session.get('user', {})
            if user.get('role') != role:
                return jsonify({'success': False, 'message': f'需要 {role} 权限'}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator


# ==================== 模块初始化 ====================

def init_auth(app) -> None:
    """
    初始化认证模块

    注册蓝图并设置 session 密钥

    参数:
        app: Flask 应用实例
    """
    # 设置 session 加密密钥（生产环境应从环境变量读取）
    app.secret_key = os.environ.get(
        'FLASK_SECRET_KEY',
        'emergency-data-system-secret-key-change-in-production'
    )
    # 会话有效期：24 小时
    app.config['PERMANENT_SESSION_LIFETIME'] = 86400
    # 注册蓝图
    app.register_blueprint(auth_bp)
    # 确保默认管理员账户存在
    _load_users()


# ==================== 独立测试入口 ====================

if __name__ == '__main__':
    print('=' * 50)
    print('  用户认证模块测试')
    print('=' * 50)

    # 测试用户加载
    users = _load_users()
    print(f'已加载用户: {list(users.keys())}')

    # 测试密码哈希
    pw_hash = generate_password_hash('test123')
    assert check_password_hash(pw_hash, 'test123'), '密码哈希验证失败'
    assert not check_password_hash(pw_hash, 'wrong'), '错误密码应验证失败'
    print('密码哈希: 正常')

    # 测试用户查找
    admin = _get_user('admin')
    assert admin is not None, '管理员账户不存在'
    assert admin['role'] == 'admin', '管理员角色不正确'
    print(f'默认管理员: {admin["username"]} ({admin["role"]})')

    # 测试不存在的用户
    nobody = _get_user('nobody')
    assert nobody is None, '不存在的用户应返回 None'
    print('不存在用户查询: 正常')

    print()
    print('=' * 50)
    print('认证模块测试通过')
