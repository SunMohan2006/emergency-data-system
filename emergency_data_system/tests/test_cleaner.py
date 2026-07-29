"""
清洗引擎单元测试（pytest）
运行: cd emergency_data_system && pytest tests/ -v
"""

import sys, os
import pytest
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from data_cleaner import (
    normalize_date, clean_phone, clean_company_name,
    standardize_columns, deduplicate_and_fill, load_excel, clean_data,
)


# ==================== 日期解析 ====================

@pytest.mark.parametrize("val,expected", [
    ('2024/1/5',      '2024-01-05'),
    ('2024年3月20日',  '2024-03-20'),
    ('20240105',       '2024-01-05'),
    ('1/5/2024',       '2024-01-05'),
    ('2024.07.20',     '2024-07-20'),
    ('2024-06-15',     '2024-06-15'),
    ('2024-1-5',       '2024-01-05'),
])
def test_normalize_date_valid(val, expected):
    """合法日期格式统一化为 YYYY-MM-DD"""
    assert normalize_date(val, 'DEFAULT') == expected


@pytest.mark.parametrize("val", [
    'bad-date', '', '   ', '2024-13-01', '2024-02-30', 'abc',
])
def test_normalize_date_invalid(val):
    """非法日期降级为默认日期"""
    assert normalize_date(val, 'DEFAULT') == 'DEFAULT'


def test_normalize_date_none():
    """None/NaN 返回默认日期"""
    assert normalize_date(None, 'DEFAULT') == 'DEFAULT'
    assert normalize_date(float('nan'), 'DEFAULT') == 'DEFAULT'


# ==================== 电话号码 ====================

@pytest.mark.parametrize("val,expected_clean,expected_valid", [
    ('13812345678',    '13812345678', True),
    ('139-1234-5678',  '13912345678', True),
    ('(010)88886666',  '01088886666', True),
    ('010-8888-6666',  '01088886666', True),
    ('+8613812345678', '13812345678', True),
    (' 13812345678 ',  '13812345678', True),
    ('12345',          '12345',       False),
    ('13800138000x',   '13800138000x', False),
    ('',               '待补充',       False),
])
def test_clean_phone(val, expected_clean, expected_valid):
    cleaned, valid, _ = clean_phone(val)
    assert cleaned == expected_clean
    assert valid == expected_valid


# ==================== 企业名称 ====================

@pytest.mark.parametrize("val,expected_clean,expected_valid", [
    (' 华为技术 ', '华为技术', True),
    ('',          '待补充',   False),
    ('无',        '待补充',   False),
    ('暂无',      '待补充',   False),
    ('华为(深圳)', '华为（深圳）', True),
    ('NaN',       '待补充',   False),
])
def test_clean_company_name(val, expected_clean, expected_valid):
    cleaned, valid, _ = clean_company_name(val)
    assert cleaned == expected_clean, f"期望 {expected_clean}, 得到 {cleaned}"
    assert valid == expected_valid


# ==================== 列名标准化 ====================

def test_standardize_columns():
    df = pd.DataFrame(columns=['企业', '公司', '手机', '电话', '日期', '地址'])
    result = standardize_columns(df)
    assert '企业名称' in result.columns
    assert '联系电话' in result.columns
    assert '排查日期' in result.columns
    assert '企业地址' in result.columns


# ==================== 去重逻辑 ====================

def test_deduplicate():
    df = pd.DataFrame({
        '企业名称': ['A公司', 'A公司', 'B公司', 'B公司'],
        '排查日期': ['2024-01-01', '2024-01-01', '2024-01-01', '2024-01-02'],
    })
    result_df, removed = deduplicate_and_fill(df)
    assert removed == 1
    assert len(result_df) == 3
    # B公司两条不同日期应都保留
    assert len(result_df[result_df['企业名称'] == 'B公司']) == 2


def test_deduplicate_no_keys():
    """没有匹配的去重键时，不剔除任何行"""
    df = pd.DataFrame({'A': ['x', 'x'], 'B': ['y', 'y']})
    result_df, removed = deduplicate_and_fill(df)
    assert removed == 0


# ==================== 文件读取 ====================

def test_load_empty_file(tmp_path):
    """空文件应抛出异常"""
    p = tmp_path / 'empty.xlsx'
    pd.DataFrame().to_excel(p, index=False)
    with pytest.raises(ValueError, match='为空'):
        load_excel(str(p))


def test_load_all_empty_rows(tmp_path):
    """全空行文件应抛出异常"""
    p = tmp_path / 'all_empty.xlsx'
    pd.DataFrame({'A': ['', None], 'B': ['', '']}).to_excel(p, index=False)
    with pytest.raises(ValueError):
        load_excel(str(p))


# ==================== 端到端清洗 ====================

def test_clean_data_end_to_end():
    """端到端测试：15条脏数据 → 13条有效"""
    test_file = os.path.join(
        os.path.dirname(__file__), '..', 'uploads', 'test_realistic.xlsx'
    )
    if not os.path.exists(test_file):
        pytest.skip('测试数据文件不存在')

    result = clean_data(test_file)
    assert result['original_count'] == 15
    assert result['valid_count'] == 13
    assert result['removed_dup_count'] == 2
    assert result['anomaly_count'] > 0
    assert os.path.exists(result['output_path'])
    assert os.path.exists(result['log_path'])
    # 辅助列不应泄露到输出
    assert '_phone_valid' not in result['columns']
    assert '_date_anomaly' not in result['columns']


def test_clean_data_column_stats():
    """应急专属字段应有分布统计"""
    test_file = os.path.join(
        os.path.dirname(__file__), '..', 'uploads', 'test_realistic.xlsx'
    )
    if not os.path.exists(test_file):
        pytest.skip('测试数据文件不存在')

    result = clean_data(test_file)
    stats = result.get('column_stats', {})
    assert '排查类型' in stats
    assert '隐患等级' in stats


# ==================== 异常日志 ====================

def test_anomaly_logs_contain_date_error():
    """日期格式无法识别应记入日志"""
    test_file = os.path.join(
        os.path.dirname(__file__), '..', 'uploads', 'test_dirty_data.xlsx'
    )
    if not os.path.exists(test_file):
        pytest.skip('测试数据文件不存在')

    result = clean_data(test_file)
    log_types = set(log['异常类型'] for log in result['anomaly_logs'])
    assert '日期格式无法识别' in log_types
