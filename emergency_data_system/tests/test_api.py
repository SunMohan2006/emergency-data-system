"""
API 接口测试（pytest）
运行前需启动 Flask: python app.py
"""

import pytest
import requests


class TestHealthCheck:
    """健康检查"""

    def test_health(self, base_url):
        r = requests.get(f'{base_url}/api/health')
        assert r.status_code == 200
        assert r.json()['status'] == 'ok'


class TestUpload:
    """上传清洗"""

    def test_no_file_returns_401(self, base_url):
        """未登录且未传文件 → 401（先触发登录拦截）"""
        r = requests.post(f'{base_url}/api/upload')
        assert r.status_code == 401

    def test_empty_filename_returns_401(self, base_url):
        r = requests.post(f'{base_url}/api/upload', files={'file': ('', b'')})
        assert r.status_code == 401

    def test_txt_format_returns_401(self, base_url):
        r = requests.post(f'{base_url}/api/upload',
                          files={'file': ('test.txt', b'hello')})
        assert r.status_code == 401

    def test_upload_without_login_returns_401(self, base_url):
        """未登录上传应被拦截"""
        with open('uploads/test_dirty_data.xlsx', 'rb') as f:
            r = requests.post(f'{base_url}/api/upload',
                              files={'file': ('test.xlsx', f)})
        assert r.status_code == 401

    def test_upload_as_admin(self, admin_session, base_url):
        """管理员上传应成功"""
        with open('uploads/test_dirty_data.xlsx', 'rb') as f:
            r = admin_session.post(f'{base_url}/api/upload',
                                   files={'file': ('test.xlsx', f)})
        assert r.status_code == 200
        data = r.json()
        assert data['success']
        assert data['data']['original_count'] == 8
        assert data['data']['valid_count'] == 7


class TestSecurity:
    """安全防护"""

    def test_path_traversal_blocked(self, base_url):
        r = requests.get(f'{base_url}/api/download/../../../etc/passwd')
        assert r.status_code in (401, 404)  # 401需要登录, 404文件不存在

    def test_nonexistent_file(self, admin_session, base_url):
        r = admin_session.get(f'{base_url}/api/download/nonexistent.xlsx')
        assert r.status_code == 404

    def test_long_filename(self, admin_session, base_url):
        long_name = 'a' * 500 + '.xlsx'
        r = admin_session.get(f'{base_url}/api/download/{long_name}')
        assert r.status_code == 404


class TestAuth:
    """认证接口"""

    def test_login_success(self, base_url):
        r = requests.post(f'{base_url}/auth/login',
                          json={'username': 'admin', 'password': 'admin123'})
        assert r.status_code == 200
        assert r.json()['success']

    def test_login_wrong_password(self, base_url):
        r = requests.post(f'{base_url}/auth/login',
                          json={'username': 'admin', 'password': 'wrong'})
        assert r.status_code == 401

    def test_login_empty_fields(self, base_url):
        r = requests.post(f'{base_url}/auth/login',
                          json={'username': '', 'password': ''})
        assert r.status_code == 400

    def test_register_and_login(self, base_url):
        """注册 → 登录 → 登出 完整流程"""
        import uuid
        username = f'test_{uuid.uuid4().hex[:6]}'

        # 注册
        r = requests.post(f'{base_url}/auth/register',
                          json={'username': username, 'password': '123456'})
        assert r.status_code == 200
        assert r.json()['success']

        # 登录
        r = requests.post(f'{base_url}/auth/login',
                          json={'username': username, 'password': '123456'})
        assert r.status_code == 200
        cookies = r.cookies

        # 查看登录状态（logged_in 在顶层）
        r = requests.get(f'{base_url}/auth/status', cookies=cookies)
        assert r.json()['logged_in']

        # 登出
        r = requests.post(f'{base_url}/auth/logout', cookies=cookies)
        assert r.json()['success']

    def test_duplicate_username(self, base_url):
        """重复用户名应拒绝"""
        r = requests.post(f'{base_url}/auth/register',
                          json={'username': 'admin', 'password': '123456'})
        assert r.status_code == 409


class TestDataEndpoints:
    """数据查询接口（需要登录）"""

    def test_stats_requires_login(self, base_url):
        r = requests.get(f'{base_url}/api/stats')
        assert r.status_code == 401

    def test_stats_as_admin(self, admin_session, base_url):
        r = admin_session.get(f'{base_url}/api/stats')
        assert r.status_code == 200
        data = r.json()
        assert data['success']
        assert 'total_records' in data['data']

    def test_monthly_as_admin(self, admin_session, base_url):
        r = admin_session.get(f'{base_url}/api/monthly')
        assert r.status_code == 200
