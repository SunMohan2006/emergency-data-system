"""pytest 共享 fixtures"""

import os, sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


@pytest.fixture(scope='session')
def base_url():
    """Flask 服务地址，依赖外部已启动的服务"""
    return 'http://127.0.0.1:5000'


@pytest.fixture(scope='session')
def admin_session(base_url):
    """已登录 admin 的 requests Session"""
    import requests  # 延迟导入，避免 CI 上无 Flask 时加载失败
    s = requests.Session()
    r = s.post(f'{base_url}/auth/login',
               json={'username': 'admin', 'password': 'admin123'})
    if not r.json().get('success'):
        pytest.skip('无法登录 admin，请确认 Flask 已启动')
    return s
