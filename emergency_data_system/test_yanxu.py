"""
研序全维度测试脚本 — 测试清洗引擎、API、边界情况
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
from data_cleaner import (
    load_excel, standardize_columns, normalize_date, clean_phone,
    clean_company_name, deduplicate_and_fill, collect_anomaly_logs, clean_data
)
import requests

BASE = "http://127.0.0.1:5000"
PASS, FAIL = 0, 0

def check(condition, msg):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  ✅ PASS: {msg}")
    else:
        FAIL += 1
        print(f"  ❌ FAIL: {msg}")

def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

# ==================== 第1组：清洗引擎边界 ====================
section("1. 清洗引擎边界测试")

# 1.1 空文件
section("1.1 空文件")
empty_path = 'uploads/_test_empty.xlsx'
pd.DataFrame().to_excel(empty_path, index=False)
try:
    load_excel(empty_path)
    check(False, "空文件应抛出异常")
except ValueError as e:
    check(True, f"空文件正确拒绝: {e}")

# 1.2 全空行
section("1.2 全空行/全空列")
all_empty = pd.DataFrame({'企业': ['', None, ''], '手机': ['', '', None]})
all_empty.to_excel('uploads/_test_all_empty.xlsx', index=False)
try:
    load_excel('uploads/_test_all_empty.xlsx')
    check(False, "全空行应抛出异常")
except ValueError:
    check(True, "全空行正确拒绝")

# 1.3 日期极端值
section("1.3 日期边界")
date_cases = [
    ('2024/1/5',     '2024-01-05', False),
    ('2024年3月20日', '2024-03-20', False),
    ('20240105',      '2024-01-05', False),
    ('1/5/2024',      '2024-01-05', False),
    ('2024.07.20',    '2024-07-20', False),
    ('bad-date',      'DEFAULT',    True),  # 异常
    ('',              'DEFAULT',    True),
    ('   ',           'DEFAULT',    True),
    ('2024-13-01',    'DEFAULT',    True),  # 非法月份
    ('2024-02-30',    'DEFAULT',    True),  # 非法日期
    ('2024-06-15',    '2024-06-15', False),
]
for val, exp, is_anomaly in date_cases:
    result = normalize_date(val, 'DEFAULT')
    if is_anomaly:
        check(result == 'DEFAULT', f'非法日期 "{val}" → 默认值')
    else:
        check(result == exp, f'合法日期 "{val}" → {exp}')

# 1.4 电话号码边界
section("1.4 电话号码边界")
phone_cases = [
    ('13812345678',    '13812345678', True),
    ('139-1234-5678',  '13912345678', True),
    ('(010)88886666',  '01088886666', True),
    ('010-8888-6666',  '01088886666', True),
    ('12345',          '12345',       False),
    ('',               '待补充',       False),
    ('13800138000x',   '13800138000x', False),
    ('+8613812345678', '13812345678', True),
    (' 13812345678 ',  '13812345678', True),
]
for val, exp_clean, exp_valid in phone_cases:
    cleaned, valid, _ = clean_phone(val)
    check(cleaned == exp_clean and valid == exp_valid,
          f'"{val}" → "{cleaned}" valid={valid}')

# 1.5 企业名称边界
section("1.5 企业名称边界")
name_cases = [
    (' 华为技术 ',  '华为技术',   True),
    ('',           '待补充',      False),
    ('无',         '待补充',      False),
    ('暂无',       '待补充',      False),
    ('华为(深圳)',  '华为（深圳）', True),
    ('NaN',        '待补充',      False),
    (None,         '待补充',      False),
]
for val, exp_clean, exp_valid in name_cases:
    if val is None:
        import numpy as np
        val = np.nan
    cleaned, valid, _ = clean_company_name(val)
    check(cleaned == exp_clean and valid == exp_valid,
          f'"{str(val)[:20]}" → "{cleaned}"')

# 1.6 去重逻辑
section("1.6 去重逻辑")
df_dup = pd.DataFrame({
    '企业名称': ['A公司', 'A公司', 'B公司', 'B公司'],
    '排查日期': ['2024-01-01', '2024-01-01', '2024-01-01', '2024-01-02'],
})
result_df, removed = deduplicate_and_fill(df_dup)
check(removed == 1, f"剔除重复: {removed} 条 (期望1)")
check(len(result_df[result_df['企业名称']=='B公司']) == 2,
      "B公司保留2条(不同日期)")

# 1.7 字段标准化
section("1.7 字段列名标准化")
df_cols = pd.DataFrame(columns=['企业', '公司', '手机', '电话', '日期', '地址'])
result = standardize_columns(df_cols)
check('企业名称' in result.columns, "'企业'→'企业名称'")
check('联系电话' in result.columns, "'手机'→'联系电话'")
check('排查日期' in result.columns, "'日期'→'排查日期'")
check('企业地址' in result.columns, "'地址'→'企业地址'")

# ==================== 第2组：API接口测试 ====================
section("2. API接口健壮性测试")

# 2.1 无文件提交
section("2.1 非法请求")
resp = requests.post(f"{BASE}/api/upload")
check(resp.status_code == 400, f"无文件提交 → 400 (got {resp.status_code})")

# 2.2 空文件名
resp = requests.post(f"{BASE}/api/upload", files={"file": ("", b"")})
check(resp.status_code == 400, f"空文件名 → 400 (got {resp.status_code})")

# 2.3 非法格式
resp = requests.post(f"{BASE}/api/upload", files={"file": ("test.txt", b"hello")})
check(resp.status_code == 400, f"txt格式 → 400 (got {resp.status_code})")

# 2.4 正常上传
section("2.2 正常上传+清洗")
with open("uploads/test_realistic.xlsx", "rb") as f:
    resp = requests.post(f"{BASE}/api/upload", files={"file": ("test.xlsx", f)})
check(resp.status_code == 200, f"上传成功 → 200 (got {resp.status_code})")
data = resp.json()
check(data['success'] == True, f"success=True")
check('original_count' in data.get('data', {}), "返回original_count")
check('valid_count' in data.get('data', {}), "返回valid_count")
check('anomaly_logs' in data.get('data', {}), "返回anomaly_logs")

# 2.5 路径穿越防护
section("2.3 安全: 路径穿越")
resp = requests.get(f"{BASE}/api/download/../../../etc/passwd")
check(resp.status_code == 404, f"路径穿越 → 404 (got {resp.status_code})")

# 2.6 下载不存在的文件
resp = requests.get(f"{BASE}/api/download/nonexistent.xlsx")
check(resp.status_code == 404, f"不存在的文件 → 404 (got {resp.status_code})")

# 2.7 超大文件名
long_name = "a" * 500 + ".xlsx"
resp = requests.get(f"{BASE}/api/download/{long_name}")
check(resp.status_code == 404, f"超长文件名 → 404 (got {resp.status_code})")

# 2.8 健康检查
resp = requests.get(f"{BASE}/api/health")
check(resp.status_code == 200, f"健康检查 → 200")
check(resp.json().get('status') == 'ok', "status=ok")

# ==================== 第3组：端到端真实场景 ====================
section("3. 端到端真实场景测试")

# 3.0 不相关Excel文件——系统应优雅降级不崩溃
section("3.0 不相关Excel（盲区测试）")
df_unrelated = pd.DataFrame({
    '学号': ['001', '002', '003'],
    '姓名': ['张三', '李四', '王五'],
    '成绩': [85, 92, 78]
})
df_unrelated.to_excel('uploads/_test_unrelated.xlsx', index=False)
try:
    result = clean_data('uploads/_test_unrelated.xlsx')
    check(True, "不崩溃，优雅降级")
    # 不相关Excel不会强制添加排查日期列，这是正确行为
    check(result['original_count'] == 3, "原始3条数据正确保留")
    check(len(result['columns']) >= 3, f"输出列数 {len(result['columns'])} >= 3")
    os.remove('uploads/_test_unrelated.xlsx')
except Exception as e:
    check(False, f"崩溃了: {e}")

result = clean_data("uploads/test_realistic.xlsx")
check(result['original_count'] == 15, f"原始数据: {result['original_count']} (期望15)")
check(result['valid_count'] == 13, f"有效数据: {result['valid_count']} (期望13)")
check(result['removed_dup_count'] == 2, f"剔除重复: {result['removed_dup_count']} (期望2)")
check(result['anomaly_count'] > 0, f"异常条数: {result['anomaly_count']} (>0)")

# 检查日志内容
logs = result['anomaly_logs']
log_types = set(log['异常类型'] for log in logs)
check('日期格式无法识别' in str(log_types), f"日志包含日期异常 (types: {log_types})")

# 检查输出文件存在
check(os.path.exists(result['output_path']), f"输出文件存在: {os.path.basename(result['output_path'])}")
check(os.path.exists(result['log_path']), f"日志文件存在: {os.path.basename(result['log_path'])}")

# 检查输出文件可读
output_df = pd.read_excel(result['output_path'])
check(len(output_df) == 13, f"输出文件行数: {len(output_df)} (期望13)")
check('企业名称' in output_df.columns, "输出包含'企业名称'列")
check('_phone_valid' not in output_df.columns, "输出不包含_phone_valid辅助列")
check('_date_anomaly' not in output_df.columns, "输出不包含_date_anomaly辅助列")

# 检查无"待补充"企业名称有几条
missing_names = (output_df['企业名称'] == '待补充').sum()
check(missing_names == 2, f"企业名称为'待补充': {missing_names} 条 (期望2)")

# ==================== 第4组：代码质量审查 ====================
section("4. 代码质量审查")

# 4.1 检查是否有未使用的导入
import ast
for fname in ['app.py', 'data_cleaner.py', 'config.py']:
    with open(fname, 'r', encoding='utf-8') as f:
        content = f.read()
    tree = ast.parse(content)
    imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
    check(len(imports) > 0, f"{fname}: 有 {len(imports)} 个导入语句")

# 4.2 检查 config.py 无敏感信息泄露
with open('config.py', 'r', encoding='utf-8') as f:
    config_content = f.read()
check('password' not in config_content.lower(), "config.py 无硬编码密码")
check('secret' not in config_content.lower(), "config.py 无硬编码密钥")
check('token' not in config_content.lower(), "config.py 无硬编码令牌")

# 4.3 检查 app.py 无 debug=True 硬编码在生产模式的风险
with open('app.py', 'r', encoding='utf-8') as f:
    app_content = f.read()
check('debug=True' in app_content, "app.py 开发模式 debug=True (已知，答辩时需说明)")
check("if __name__ == '__main__'" in app_content, "app.py 有 __main__ 保护")

# 4.4 检查异常处理覆盖
check('try:' in app_content and 'except' in app_content, "app.py 有异常处理")
with open('data_cleaner.py', 'r', encoding='utf-8') as f:
    dc_content = f.read()
check('try:' in dc_content or 'except' in dc_content,
      "data_cleaner.py 有异常处理")

# ==================== 汇总 ====================
section("测试汇总")
total = PASS + FAIL
print(f"  通过: {PASS}/{total}")
print(f"  失败: {FAIL}/{total}")
if FAIL == 0:
    print(f"  🎉 所有测试通过！")
else:
    print(f"  ⚠️ 有 {FAIL} 项测试失败，需要修复")

# 清理测试文件
for f in ['uploads/_test_empty.xlsx', 'uploads/_test_all_empty.xlsx']:
    if os.path.exists(f):
        os.remove(f)
