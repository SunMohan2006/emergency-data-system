"""
系统配置文件
可在此修改清洗规则参数、地域前缀、文件路径等
"""

import os

# ==================== 路径配置 ====================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
OUTPUT_FOLDER = os.path.join(BASE_DIR, 'outputs')
LOG_FOLDER = os.path.join(BASE_DIR, 'logs')

# 确保目录存在
for folder in [UPLOAD_FOLDER, OUTPUT_FOLDER, LOG_FOLDER]:
    os.makedirs(folder, exist_ok=True)

# ==================== 上传配置 ====================
ALLOWED_EXTENSIONS = {'xlsx'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# ==================== 清洗规则配置 ====================

# 字段列名标准化映射（实际列名 → 标准列名）
COLUMN_STANDARD_MAP = {
    # 企业名称相关
    '企业': '企业名称',
    '公司': '企业名称',
    '单位': '企业名称',
    '企业名': '企业名称',
    '公司名称': '企业名称',
    '单位名称': '企业名称',
    # 联系电话相关
    '手机': '联系电话',
    '电话': '联系电话',
    '手机号': '联系电话',
    '手机号码': '联系电话',
    '电话号码': '联系电话',
    '联系手机': '联系电话',
    '联系号码': '联系电话',
    # 地址相关
    '地址': '企业地址',
    '所在地': '企业地址',
    '公司地址': '企业地址',
    '单位地址': '企业地址',
    '详细地址': '企业地址',
    # 排查日期相关
    '日期': '排查日期',
    '排查时间': '排查日期',
    '检查日期': '排查日期',
    '上报日期': '排查日期',
    '录入日期': '排查日期',
}

# 必填字段（这些字段为空时标记为异常）
REQUIRED_FIELDS = ['企业名称', '联系电话', '排查日期']

# 去重维度（这些字段组合完全一致视为重复）
DEDUP_KEYS = ['企业名称', '排查日期']

# 空白字段填充值
FILL_VALUE = '待补充'

# 地域前缀配置（根据辖区修改）
REGION_PREFIX = {
    'province': '',   # 如 'XX省'
    'city': '',       # 如 'XX市'
    'district': '',   # 如 'XX区/县'
}
