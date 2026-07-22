"""
应急数据智能清洗引擎
基于 Pandas 定制清洗规则，覆盖字段标准化、格式校验、去重填充、异常日志全流程
"""

import re
import os
from datetime import datetime
from typing import Tuple, List, Dict, Any

import pandas as pd
from openpyxl import load_workbook
from openpyxl.styles import Font

from config import (
    COLUMN_STANDARD_MAP,
    REQUIRED_FIELDS,
    DEDUP_KEYS,
    FILL_VALUE,
    REGION_PREFIX,
    OUTPUT_FOLDER,
)


# ====================================================================
# 【小节3.1】Excel 文件读取
# ====================================================================

def load_excel(file_path: str) -> pd.DataFrame:
    """
    读取上传的 Excel 文件（.xlsx 格式）

    参数:
        file_path: Excel 文件路径

    返回:
        pd.DataFrame: 读取到的数据表

    异常:
        ValueError: 文件格式不支持或读取失败
    """
    if not os.path.exists(file_path):
        raise ValueError(f"文件不存在: {file_path}")

    ext = os.path.splitext(file_path)[1].lower()

    if ext == '.xlsx':
        df = pd.read_excel(file_path, engine='openpyxl', dtype=str)
    else:
        raise ValueError(f"不支持的文件格式: {ext}，仅支持 .xlsx 格式")

    if df.empty:
        raise ValueError("文件内容为空，请检查上传文件")

    # 去除全空行和全空列
    df = df.dropna(how='all').dropna(axis=1, how='all')

    return df


# ====================================================================
# 【小节3.2】字段列名标准化
# ====================================================================

def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    智能统一差异化字段命名
    例：'企业'/'公司'/'单位' → '企业名称'
        '手机'/'电话'/'手机号' → '联系电话'

    参数:
        df: 原始 DataFrame

    返回:
        列名标准化后的 DataFrame
    """
    # 去除列名首尾空格
    df.columns = [str(col).strip() for col in df.columns]

    rename_map = {}
    for col in df.columns:
        if col in COLUMN_STANDARD_MAP:
            rename_map[col] = COLUMN_STANDARD_MAP[col]

    if rename_map:
        df = df.rename(columns=rename_map)

    return df


# ====================================================================
# 【小节3.3】日期格式规范化
# ====================================================================

def normalize_date(value: Any, default_date: str = None) -> str:
    """
    将各种不规则日期格式统一为 YYYY-MM-DD

    支持的输入格式示例：
        - 2024/1/5
        - 2024年1月5日
        - 2024.1.5
        - 20240105
        - 1/5/2024
        - 空值/NaN → 用默认日期填充

    参数:
        value: 原始日期值
        default_date: 默认日期（如上报当日），格式 YYYY-MM-DD

    返回:
        标准化后的日期字符串 YYYY-MM-DD
    """
    if default_date is None:
        default_date = datetime.now().strftime('%Y-%m-%d')

    if pd.isna(value) or str(value).strip() == '' or str(value).strip() in ('nan', 'NaN', 'None', ''):
        return default_date

    date_str = str(value).strip()

    # 清理常见分隔符，统一为 -
    # 先处理中文格式：2024年1月5日
    chinese_match = re.match(r'(\d{4})年(\d{1,2})月(\d{1,2})日?', date_str)
    if chinese_match:
        y, m, d = chinese_match.groups()
        return f'{int(y):04d}-{int(m):02d}-{int(d):02d}'

    # 替换 . / 为 -
    date_str_clean = re.sub(r'[./]', '-', date_str)

    # 纯数字 20240105
    if date_str_clean.isdigit() and len(date_str_clean) == 8:
        y, m, d = date_str_clean[:4], date_str_clean[4:6], date_str_clean[6:8]
        return f'{int(y):04d}-{int(m):02d}-{int(d):02d}'

    # 尝试解析标准格式
    patterns = [
        (r'^(\d{4})-(\d{1,2})-(\d{1,2})$', None),   # 2024-1-5
        (r'^(\d{1,2})-(\d{1,2})-(\d{4})$', 'md'),    # 1-5-2024
    ]

    for pattern, mode in patterns:
        match = re.match(pattern, date_str_clean)
        if match:
            g = match.groups()
            if mode == 'md':
                m, d, y = g
            else:
                y, m, d = g
            try:
                y, m, d = int(y), int(m), int(d)
                if 2000 <= y <= 2100 and 1 <= m <= 12 and 1 <= d <= 31:
                    # 验证日期合法性
                    datetime(y, m, d)
                    return f'{y:04d}-{m:02d}-{d:02d}'
            except (ValueError, OverflowError):
                pass

    # 所有规则都不匹配，返回默认日期
    return default_date


def normalize_dates_in_df(df: pd.DataFrame, date_column: str = '排查日期') -> pd.DataFrame:
    """
    对 DataFrame 中指定日期列进行批量规范化，并标记日期异常

    参数:
        df: 数据表
        date_column: 日期列名

    返回:
        日期列已规范化的 DataFrame（附加 _date_anomaly 和 _date_original 辅助列）
    """
    if date_column not in df.columns:
        df[date_column] = datetime.now().strftime('%Y-%m-%d')
        return df

    # 保存原始值用于异常检测
    original_values = df[date_column].copy()
    default = datetime.now().strftime('%Y-%m-%d')
    df[date_column] = df[date_column].apply(lambda v: normalize_date(v, default))

    # 标记日期异常：原始值非空但无法解析的（被替换为默认日期的）
    df['_date_anomaly'] = False
    df['_date_original'] = ''
    for i in df.index:
        orig = str(original_values[i]).strip()
        if orig and orig not in ('nan', 'NaN', 'None', ''):
            # 检查 normalize_date 是否成功解析
            test_result = normalize_date(orig, '__TEST__')
            if test_result == '__TEST__':
                df.at[i, '_date_anomaly'] = True
                df.at[i, '_date_original'] = orig

    return df


# ====================================================================
# 【小节3.4】联系方式智能校验
# ====================================================================

def clean_phone(phone: Any) -> Tuple[str, bool, str]:
    """
    清洗并校验电话号码

    处理流程：
        1. 去除空格、横线、括号等无效字符
        2. 校验是否为合法手机号（11位，1开头）
        3. 校验是否为合法固话（区号+号码）

    参数:
        phone: 原始电话号码

    返回:
        (清洗后号码, 是否合法, 异常原因)
    """
    if pd.isna(phone) or str(phone).strip() == '':
        return (FILL_VALUE, False, '联系电话为空')

    raw = str(phone).strip()

    # 清除无效字符，保留数字和 +
    cleaned = re.sub(r'[\s\-\(\)（）\-\.]', '', raw)

    # 空号码
    if not cleaned:
        return (FILL_VALUE, False, '联系电话为空')

    # 手机号校验：11位，以1开头
    if re.match(r'^1[3-9]\d{9}$', cleaned):
        return (cleaned, True, '')

    # 固话校验：区号(3-4位) + 号码(7-8位)
    if re.match(r'^0\d{2,3}\d{7,8}$', cleaned):
        return (cleaned, True, '')

    # 带国家码 +86
    if re.match(r'^\+86\d{11}$', cleaned):
        return (cleaned[3:], True, '')

    # 不合法
    return (raw, False, f'联系电话格式不正确: {raw}')


def clean_phones_in_df(df: pd.DataFrame, phone_column: str = '联系电话') -> pd.DataFrame:
    """
    批量清洗 DataFrame 中的联系电话列

    参数:
        df: 数据表
        phone_column: 电话列名

    返回:
        电话列已清洗的 DataFrame，异常信息记录在 _phone_valid 和 _phone_error 辅助列
    """
    if phone_column not in df.columns:
        return df

    results = df[phone_column].apply(clean_phone)
    df[phone_column] = results.apply(lambda r: r[0])
    df['_phone_valid'] = results.apply(lambda r: r[1])
    df['_phone_error'] = results.apply(lambda r: r[2])

    return df


# ====================================================================
# 【小节3.5】企业名称规整
# ====================================================================

def clean_company_name(name: Any) -> Tuple[str, bool, str]:
    """
    规整企业名称：去空格、统一括号、检查空值

    参数:
        name: 原始企业名称

    返回:
        (规整后名称, 是否有效, 异常原因)
    """
    if pd.isna(name) or str(name).strip() == '':
        return (FILL_VALUE, False, '企业名称为空')

    cleaned = str(name).strip()

    # 统一中英文括号：全角 → 半角（保持一致性）
    # 注：中文环境通常保留全角括号，但统一为全角更规范
    cleaned = cleaned.replace('(', '（').replace(')', '）')

    # 去除多余空格
    cleaned = re.sub(r'\s+', '', cleaned)

    if not cleaned or cleaned in ('nan', 'NaN', 'None', '无', '暂无'):
        return (FILL_VALUE, False, f'企业名称为无效值: {name}')

    return (cleaned, True, '')


# ====================================================================
# 【小节3.6】地址自适应补全
# ====================================================================

def complete_address(address: Any) -> str:
    """
    自动补全缺失地域前缀的地址

    根据 config.py 中的 REGION_PREFIX 配置，
    自动为缺少省/市/区前缀的地址补全地域信息

    参数:
        address: 原始地址字符串

    返回:
        补全后的地址
    """
    if pd.isna(address) or str(address).strip() == '':
        return FILL_VALUE

    addr = str(address).strip()

    # 拼接配置中的地域前缀
    prefix_parts = []
    for key in ['province', 'city', 'district']:
        val = REGION_PREFIX.get(key, '')
        if val:
            prefix_parts.append(val)

    full_prefix = ''.join(prefix_parts)

    if not full_prefix:
        return addr  # 未配置前缀，原样返回

    # 如果地址已经包含前缀，不重复添加
    if addr.startswith(full_prefix):
        return addr

    # 逐级检查
    for key in ['district', 'city', 'province']:
        val = REGION_PREFIX.get(key, '')
        if val and not addr.startswith(val):
            # 找到第一个缺失的级别，补全它及后面的所有级别
            prefix_parts = []
            for k in ['province', 'city', 'district']:
                v = REGION_PREFIX.get(k, '')
                if v and (k == key or not addr.startswith(v)):
                    prefix_parts.append(v)
            full_prefix = ''.join(prefix_parts)
            return full_prefix + addr

    return addr


def complete_addresses_in_df(df: pd.DataFrame, addr_column: str = '企业地址') -> pd.DataFrame:
    """
    批量补全地址列

    参数:
        df: 数据表
        addr_column: 地址列名

    返回:
        地址已补全的 DataFrame
    """
    if addr_column in df.columns:
        df[addr_column] = df[addr_column].apply(complete_address)
    return df


# ====================================================================
# 【小节3.6】数据去重 + 缺失填充
# ====================================================================

def deduplicate_and_fill(df: pd.DataFrame) -> Tuple[pd.DataFrame, int]:
    """
    以核心维度去重，并对空白字段统一填充

    去重维度：企业名称 + 排查日期（可在 config.py 的 DEDUP_KEYS 中修改）
    填充值：'待补充'（可在 config.py 的 FILL_VALUE 中修改）

    参数:
        df: 数据表

    返回:
        (去重填充后的 DataFrame, 被剔除的重复行数)
    """
    original_count = len(df)

    # 去重：保留第一次出现的记录
    dedup_keys = [k for k in DEDUP_KEYS if k in df.columns]
    if dedup_keys:
        df = df.drop_duplicates(subset=dedup_keys, keep='first')

    removed_count = original_count - len(df)

    # 空白字段统一填充
    df = df.fillna(FILL_VALUE)
    # 空字符串也填充
    df = df.replace(r'^\s*$', FILL_VALUE, regex=True)

    return df, removed_count


# ====================================================================
# 【小节3.6】异常日志收集
# ====================================================================

def collect_anomaly_logs(df: pd.DataFrame) -> List[Dict[str, str]]:
    """
    收集所有异常数据记录，生成清洗日志

    检查项：
        1. 必填字段为空/填充值
        2. 电话号码不合法
        3. 企业名称为填充值
        4. 日期格式异常（已由 normalize_date 处理，此处检测残留）

    参数:
        df: 清洗后的 DataFrame

    返回:
        异常日志列表，每条格式: {行号, 字段, 原始值, 异常类型, 处理方式}
    """
    logs = []

    for idx, row in df.iterrows():
        row_num = idx + 2  # Excel 行号（+2 补偿0-based和表头）

        # 检查必填字段
        for field in REQUIRED_FIELDS:
            if field in df.columns:
                val = row.get(field, '')
                if str(val).strip() == FILL_VALUE or str(val).strip() == '':
                    logs.append({
                        '行号': row_num,
                        '字段': field,
                        '原始值': str(val),
                        '异常类型': '必填字段缺失',
                        '处理方式': f'已填充为"{FILL_VALUE}"'
                    })

        # 检查电话号码（来源于 _phone_valid 辅助列）
        if '_phone_valid' in df.columns:
            is_valid = row.get('_phone_valid', True)
            if str(is_valid) == 'False':
                logs.append({
                    '行号': row_num,
                    '字段': '联系电话',
                    '原始值': row.get('_phone_error', ''),
                    '异常类型': '联系方式格式错误',
                    '处理方式': '已标记，建议人工复核修改'
                })

        # 检查企业名称
        if '企业名称' in df.columns:
            name = row.get('企业名称', '')
            if str(name).strip() == FILL_VALUE:
                logs.append({
                    '行号': row_num,
                    '字段': '企业名称',
                    '原始值': '(空)',
                    '异常类型': '企业名称缺失',
                    '处理方式': f'已填充为"{FILL_VALUE}"，建议人工补录'
                })

        # 检查日期异常
        if '_date_anomaly' in df.columns:
            is_date_anomaly = row.get('_date_anomaly', False)
            if str(is_date_anomaly) == 'True':
                logs.append({
                    '行号': row_num,
                    '字段': '排查日期',
                    '原始值': row.get('_date_original', ''),
                    '异常类型': '日期格式无法识别',
                    '处理方式': '已填充为上报当日日期，建议人工复核'
                })

    return logs


def save_anomaly_logs(logs: List[Dict], file_path: str = None) -> str:
    """
    将异常日志保存为 Excel 文件

    参数:
        logs: 异常日志列表
        file_path: 保存路径（可选，默认自动生成带时间戳的文件名）

    返回:
        日志文件路径
    """
    if file_path is None:
        from config import LOG_FOLDER
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        file_path = os.path.join(LOG_FOLDER, f'清洗日志_{timestamp}.xlsx')

    if logs:
        log_df = pd.DataFrame(logs)
        log_df.to_excel(file_path, index=False, engine='openpyxl')
    else:
        # 无异常也生成日志（空日志）
        log_df = pd.DataFrame([{'备注': '本次清洗未发现异常数据'}])
        log_df.to_excel(file_path, index=False, engine='openpyxl')

    return file_path


# ====================================================================
# 【整合入口】一键清洗：调用上述所有子模块
# ====================================================================

def clean_data(file_path: str) -> Dict[str, Any]:
    """
    一键智能清洗入口函数

    完整执行流程：
        3.1 读取 Excel     → df
        3.2 列名标准化      → df
        3.3 日期规范化      → df
        3.4 号码校验       → df（附加 _phone_valid / _phone_error 辅助列）
        3.5 名称规整       → df
        3.6 地址补全       → df
        3.6 去重 + 填充    → df, removed_count
        3.6 异常日志收集   → logs
        保存清洗结果       → output_path
        保存异常日志       → log_path

    参数:
        file_path: 原始 Excel 文件路径

    返回:
        包含统计信息的字典:
        {
            'original_count': 原始数据条数,
            'valid_count': 有效数据条数,
            'removed_dup_count': 剔除重复条数,
            'anomaly_count': 异常数据条数,
            'output_path': 清洗后文件路径,
            'log_path': 异常日志文件路径,
            'columns': 清洗后的列名列表,
        }
    """
    # ---- 3.1 读取 ----
    df = load_excel(file_path)
    original_count = len(df)

    # ---- 3.2 列名标准化 ----
    df = standardize_columns(df)

    # ---- 3.3 日期规范化 ----
    if '排查日期' in df.columns or any('日期' in c for c in df.columns):
        date_col = '排查日期' if '排查日期' in df.columns else None
        if date_col is None:
            for c in df.columns:
                if '日期' in c:
                    date_col = c
                    break
        df = normalize_dates_in_df(df, date_col or '排查日期')

    # ---- 3.4 号码校验 ----
    if '联系电话' in df.columns:
        df = clean_phones_in_df(df, '联系电话')

    # ---- 3.5 企业名称规整 ----
    if '企业名称' in df.columns:
        name_results = df['企业名称'].apply(clean_company_name)
        df['企业名称'] = name_results.apply(lambda r: r[0])
        # 名称无效的也标记在日志中
    else:
        # 尝试找到名称相关的列
        name_col = None
        for c in df.columns:
            if '名称' in c or '企业' in c or '公司' in c or '单位' in c:
                name_col = c
                break
        if name_col:
            df = df.rename(columns={name_col: '企业名称'})
            df['企业名称'] = df['企业名称'].apply(lambda n: clean_company_name(n)[0])

    # ---- 3.6 地址补全 ----
    if '企业地址' in df.columns:
        df = complete_addresses_in_df(df, '企业地址')

    # ---- 3.6 去重 + 填充 ----
    df, removed_count = deduplicate_and_fill(df)

    # ---- 3.6 异常日志 ----
    logs = collect_anomaly_logs(df)

    # 计算异常条数（去重：同一行号只算一条）
    anomaly_rows = set(log['行号'] for log in logs)
    anomaly_count = len(anomaly_rows)

    # ---- 保存清洗结果 ----
    # 移除辅助列
    output_df = df.drop(columns=['_phone_valid', '_phone_error', '_date_anomaly', '_date_original'], errors='ignore')

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_filename = f'清洗后数据_{timestamp}.xlsx'
    output_path = os.path.join(OUTPUT_FOLDER, output_filename)
    output_df.to_excel(output_path, index=False, engine='openpyxl')

    # ---- 标注"待补充"单元格为黄色字体 ----
    YELLOW_FONT = Font(color='FFA500', bold=True)
    wb = load_workbook(output_path)
    ws = wb.active
    for row in ws.iter_rows(min_row=1, max_row=ws.max_row, max_col=ws.max_column):
        for cell in row:
            if cell.value and str(cell.value).strip() == FILL_VALUE:
                cell.font = YELLOW_FONT
    wb.save(output_path)

    # ---- 保存异常日志 ----
    log_path = save_anomaly_logs(logs)

    # ---- 返回统计信息 ----
    return {
        'original_count': original_count,
        'valid_count': len(output_df),
        'removed_dup_count': removed_count,
        'anomaly_count': anomaly_count,
        'output_path': output_path,
        'log_path': log_path,
        'columns': list(output_df.columns),
        'anomaly_logs': logs,
    }


# ====================================================================
# 【独立测试入口】直接运行此文件可测试清洗引擎
# ====================================================================

if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print('用法: python data_cleaner.py <Excel文件路径>')
        print('示例: python data_cleaner.py test_data.xlsx')
        sys.exit(1)

    test_file = sys.argv[1]
    print(f'正在清洗: {test_file}')
    print('=' * 50)

    result = clean_data(test_file)

    print(f'原始数据条数: {result["original_count"]}')
    print(f'有效数据条数: {result["valid_count"]}')
    print(f'剔除重复条数: {result["removed_dup_count"]}')
    print(f'异常数据条数: {result["anomaly_count"]}')
    print(f'清洗后文件:   {result["output_path"]}')
    print(f'异常日志文件: {result["log_path"]}')
    print(f'数据列名:     {result["columns"]}')
    print('=' * 50)
    print('✅ 清洗完成！')
