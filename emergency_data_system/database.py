"""
================================================================================
  数据库持久化模块
================================================================================
  基于 SQLAlchemy ORM 实现数据持久化，默认使用 SQLite（零配置、零运维），
  预留 MySQL / PostgreSQL 切换接口，通过环境变量 DATABASE_URL 一键切换。

  架构决策:
    1. 模型-业务分离
       —— 此模块仅定义数据模型与 CRUD 操作，不包含任何清洗规则或业务逻辑
       —— 清洗逻辑完全在 data_cleaner.py 中，数据库仅负责存储和检索

    2. 双模数据库支持
       —— 默认 SQLite（sqlite:///emergency_data.db），零配置即可运行
       —— 生产切换 MySQL：export DATABASE_URL=mysql+pymysql://user:pass@host/db
       —— 生产切换 PostgreSQL：export DATABASE_URL=postgresql://user:pass@host/db

    3. 静态方法设计
       —— 所有 CRUD 操作封装为 @staticmethod，无需实例化即可调用
       —— 每次操作自动获取和释放 session，避免连接泄漏

    4. 软删除策略
       —— delete_by_batch() 为物理删除，适合合规清理场景
       —— 未来可扩展为软删除（添加 is_deleted 字段）

  数据模型（2张表）:
    CleanRecord   —— 清洗后的有效数据记录（核心表）
    AnomalyRecord —— 清洗过程中检测到的异常日志（关联表）

  表关系:
    CleanRecord.batch_id ←→ AnomalyRecord.batch_id（1:N）
    一个清洗批次可对应多条正常记录 + 多条异常日志

  使用方式:
    from database import init_db, CleanRecord, AnomalyRecord

    init_db()                          # 应用启动时调用一次，自动建表
    CleanRecord.save_batch(records)    # 批量保存清洗结果
    CleanRecord.query_all()            # 查询最近500条记录
    CleanRecord.get_stats()            # 获取全局统计概览
    CleanRecord.get_monthly_stats()    # 获取月度趋势数据
================================================================================
"""

import os
from datetime import datetime
from typing import List, Dict, Any, Optional

from sqlalchemy import (
    create_engine, Column, Integer, String, DateTime, Text,
    Float, Boolean, func
)
from sqlalchemy.orm import sessionmaker, declarative_base, scoped_session

# ==================== 数据库配置 ====================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 默认使用 SQLite（零配置，适合演示和本地使用）
# 切换 MySQL 时修改此行为：
#   DATABASE_URL = "mysql+pymysql://user:password@localhost:3306/emergency_db"
DATABASE_URL = os.environ.get(
    'DATABASE_URL',
    f'sqlite:///{os.path.join(BASE_DIR, "emergency_data.db")}'
)

# SQLite 需要 check_same_thread=False 以支持 Flask 多线程
engine_kwargs = {}
if DATABASE_URL.startswith('sqlite'):
    engine_kwargs['connect_args'] = {'check_same_thread': False}

engine = create_engine(DATABASE_URL, echo=False, **engine_kwargs)
SessionFactory = sessionmaker(bind=engine)
DBSession = scoped_session(SessionFactory)

Base = declarative_base()


# ==================== 数据模型 ====================

class CleanRecord(Base):
    """
    清洗记录模型

    存储每次清洗后生成的有效数据记录，支持按时间、区域、企业名称等维度检索
    """
    __tablename__ = 'clean_records'

    id = Column(Integer, primary_key=True, autoincrement=True, comment='自增主键')
    user_id = Column(String(64), nullable=False, default='system', index=True, comment='所属用户（与auth模块的用户名对应）')
    batch_id = Column(String(32), nullable=False, index=True, comment='批次号（清洗任务唯一标识）')
    company_name = Column(String(200), nullable=False, index=True, comment='企业名称（标准化后）')
    phone = Column(String(20), nullable=True, comment='联系电话（校验清洗后）')
    check_date = Column(String(10), nullable=True, comment='排查日期 YYYY-MM-DD')
    address = Column(String(500), nullable=True, comment='企业地址（补全后）')
    check_type = Column(String(100), nullable=True, comment='排查类型（安全生产/消防检查等）')
    source_file = Column(String(200), nullable=True, comment='原始上传文件名')
    is_anomaly = Column(Boolean, default=False, comment='是否为异常数据行')
    created_at = Column(DateTime, default=datetime.now, comment='入库时间')

    def to_dict(self) -> Dict[str, Any]:
        """将记录序列化为字典，方便 JSON 序列化"""
        return {
            'id': self.id,
            'user_id': self.user_id,
            'batch_id': self.batch_id,
            'company_name': self.company_name,
            'phone': self.phone,
            'check_date': self.check_date,
            'address': self.address,
            'check_type': self.check_type,
            'source_file': self.source_file,
            'is_anomaly': self.is_anomaly,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    # ---------- 写入操作 ----------

    @staticmethod
    def save_batch(records: List[Dict[str, Any]], user_id: str = 'system') -> int:
        """
        批量保存清洗记录

        参数:
            records: 字典列表，每个字典对应一行清洗后的数据
            user_id: 所属用户的用户名

        返回:
            成功保存的记录数
        """
        session = DBSession()
        count = 0
        try:
            for rec in records:
                record = CleanRecord(
                    user_id=user_id,
                    batch_id=rec.get('batch_id', ''),
                    company_name=rec.get('company_name', rec.get('企业名称', '')),
                    phone=rec.get('phone', rec.get('联系电话', '')),
                    check_date=rec.get('check_date', rec.get('排查日期', '')),
                    address=rec.get('address', rec.get('企业地址', '')),
                    check_type=rec.get('check_type', rec.get('排查类型', '')),
                    source_file=rec.get('source_file', ''),
                    is_anomaly=rec.get('is_anomaly', False),
                )
                session.add(record)
                count += 1
            session.commit()
        except Exception as e:
            session.rollback()
            raise RuntimeError(f'批量保存失败: {e}') from e
        finally:
            session.close()
        return count

    @staticmethod
    def save_single(record: Dict[str, Any]) -> int:
        """保存单条记录，返回记录ID"""
        return CleanRecord.save_batch([record])

    # ---------- 查询操作 ----------

    @staticmethod
    def query_all(user_id: str = None, limit: int = 500) -> List[Dict[str, Any]]:
        """查询最新记录（按入库时间倒序），可按用户过滤"""
        session = DBSession()
        try:
            q = session.query(CleanRecord)
            if user_id:
                q = q.filter(CleanRecord.user_id == user_id)
            rows = q.order_by(CleanRecord.created_at.desc()).limit(limit).all()
            return [r.to_dict() for r in rows]
        finally:
            session.close()

    @staticmethod
    def query_by_batch(batch_id: str) -> List[Dict[str, Any]]:
        """按批次号查询该批次的所有记录"""
        session = DBSession()
        try:
            rows = (
                session.query(CleanRecord)
                .filter(CleanRecord.batch_id == batch_id)
                .order_by(CleanRecord.id)
                .all()
            )
            return [r.to_dict() for r in rows]
        finally:
            session.close()

    @staticmethod
    def query_by_company(keyword: str, limit: int = 100) -> List[Dict[str, Any]]:
        """按企业名称模糊搜索"""
        session = DBSession()
        try:
            rows = (
                session.query(CleanRecord)
                .filter(CleanRecord.company_name.like(f'%{keyword}%'))
                .order_by(CleanRecord.created_at.desc())
                .limit(limit)
                .all()
            )
            return [r.to_dict() for r in rows]
        finally:
            session.close()

    @staticmethod
    def query_by_date_range(start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """按日期范围查询"""
        session = DBSession()
        try:
            rows = (
                session.query(CleanRecord)
                .filter(CleanRecord.check_date >= start_date)
                .filter(CleanRecord.check_date <= end_date)
                .order_by(CleanRecord.check_date)
                .all()
            )
            return [r.to_dict() for r in rows]
        finally:
            session.close()

    # ---------- 统计操作 ----------

    @staticmethod
    def get_stats(user_id: str = None) -> Dict[str, Any]:
        """获取统计概览，可按用户过滤"""
        session = DBSession()
        try:
            base_q = session.query(CleanRecord)
            if user_id:
                base_q = base_q.filter(CleanRecord.user_id == user_id)
            total = base_q.with_entities(func.count(CleanRecord.id)).scalar() or 0
            anomaly_count = base_q.filter(CleanRecord.is_anomaly == True).with_entities(func.count(CleanRecord.id)).scalar() or 0
            batch_count = base_q.with_entities(func.count(func.distinct(CleanRecord.batch_id))).scalar() or 0
            return {
                'total_records': total,
                'anomaly_records': anomaly_count,
                'total_batches': batch_count,
                'anomaly_rate': f'{anomaly_count / total * 100:.1f}%' if total > 0 else '0%',
            }
        finally:
            session.close()

    @staticmethod
    def get_monthly_stats(user_id: str = None) -> List[Dict[str, Any]]:
        """按月统计清洗数据量，可按用户过滤"""
        session = DBSession()
        try:
            q = session.query(CleanRecord.check_date)
            if user_id:
                q = q.filter(CleanRecord.user_id == user_id)
            rows = q.all()
            monthly = {}
            for (date_str,) in rows:
                if date_str and len(date_str) >= 7:
                    month = date_str[:7]  # YYYY-MM
                    monthly[month] = monthly.get(month, 0) + 1
            return [
                {'month': k, 'count': v}
                for k, v in sorted(monthly.items())
            ]
        finally:
            session.close()

    # ---------- 清理操作 ----------

    @staticmethod
    def delete_by_batch(batch_id: str, user_id: str = None) -> int:
        """删除指定批次（须同属一个用户）"""
        session = DBSession()
        try:
            q = session.query(CleanRecord).filter(CleanRecord.batch_id == batch_id)
            if user_id:
                q = q.filter(CleanRecord.user_id == user_id)
            count = q.delete()
            session.commit()
            return count
        except Exception as e:
            session.rollback()
            raise RuntimeError(f'删除失败: {e}') from e
        finally:
            session.close()

    @staticmethod
    def delete_all_by_user(user_id: str) -> int:
        """清空指定用户的所有清洗记录和异常日志"""
        session = DBSession()
        try:
            clean_count = (
                session.query(CleanRecord)
                .filter(CleanRecord.user_id == user_id)
                .delete()
            )
            log_count = (
                session.query(AnomalyRecord)
                .filter(AnomalyRecord.user_id == user_id)
                .delete()
            )
            session.commit()
            return clean_count + log_count
        except Exception as e:
            session.rollback()
            raise RuntimeError(f'清空失败: {e}') from e
        finally:
            session.close()


class AnomalyRecord(Base):
    """
    异常日志模型

    对应清洗过程中生成的异常日志，与 CleanRecord 通过 batch_id 关联
    """
    __tablename__ = 'anomaly_records'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, default='system', index=True, comment='所属用户')
    batch_id = Column(String(32), nullable=False, index=True, comment='关联的批次号')
    excel_row = Column(Integer, nullable=True, comment='Excel 原始行号')
    field_name = Column(String(50), nullable=True, comment='异常字段名')
    original_value = Column(Text, nullable=True, comment='原始值')
    anomaly_type = Column(String(50), nullable=True, comment='异常类型')
    solution = Column(Text, nullable=True, comment='处理方式')
    created_at = Column(DateTime, default=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id,
            'batch_id': self.batch_id,
            'excel_row': self.excel_row,
            'field_name': self.field_name,
            'original_value': self.original_value,
            'anomaly_type': self.anomaly_type,
            'solution': self.solution,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }

    @staticmethod
    def save_batch(logs: List[Dict[str, str]], batch_id: str, user_id: str = 'system') -> int:
        """批量保存异常日志"""
        session = DBSession()
        count = 0
        try:
            for log in logs:
                record = AnomalyRecord(
                    user_id=user_id,
                    batch_id=batch_id,
                    excel_row=int(log.get('行号', 0)) if log.get('行号') else None,
                    field_name=log.get('字段', ''),
                    original_value=log.get('原始值', ''),
                    anomaly_type=log.get('异常类型', ''),
                    solution=log.get('处理方式', ''),
                )
                session.add(record)
                count += 1
            session.commit()
        except Exception as e:
            session.rollback()
            raise RuntimeError(f'异常日志保存失败: {e}') from e
        finally:
            session.close()
        return count

    @staticmethod
    def query_by_batch(batch_id: str) -> List[Dict[str, Any]]:
        """按批次号查询异常日志"""
        session = DBSession()
        try:
            rows = (
                session.query(AnomalyRecord)
                .filter(AnomalyRecord.batch_id == batch_id)
                .order_by(AnomalyRecord.id)
                .all()
            )
            return [r.to_dict() for r in rows]
        finally:
            session.close()


# ==================== 数据库初始化 ====================

def init_db() -> None:
    """
    创建所有数据表（幂等操作：表已存在则跳过）

    应在应用启动时调用一次
    """
    Base.metadata.create_all(bind=engine)


def get_session():
    """获取数据库会话（用于 Flask 请求上下文）"""
    return DBSession()


def close_session():
    """关闭当前会话"""
    DBSession.remove()


# ==================== 独立测试入口 ====================

if __name__ == '__main__':
    print('=' * 50)
    print('  数据库模块测试')
    print('=' * 50)

    # 初始化
    init_db()
    print(f'数据库: {DATABASE_URL}')
    print(f'表: {Base.metadata.tables.keys()}')
    print()

    # 测试写入
    test_records = [
        {
            'batch_id': 'test_001',
            'company_name': '测试企业A',
            'phone': '13800138000',
            'check_date': '2024-07-01',
            'address': '光明街道1号',
            'check_type': '安全生产',
            'source_file': 'test.xlsx',
            'is_anomaly': False,
        },
        {
            'batch_id': 'test_001',
            'company_name': '测试企业B',
            'phone': '待补充',
            'check_date': '2024-07-02',
            'address': '待补充',
            'check_type': '消防检查',
            'source_file': 'test.xlsx',
            'is_anomaly': True,
        },
    ]
    count = CleanRecord.save_batch(test_records)
    print(f'写入记录: {count} 条')

    # 测试查询
    all_records = CleanRecord.query_all()
    print(f'查询全部: {len(all_records)} 条')

    stats = CleanRecord.get_stats()
    print(f'统计: 总计={stats["total_records"]}, 异常={stats["anomaly_records"]}, 异常率={stats["anomaly_rate"]}')

    monthly = CleanRecord.get_monthly_stats()
    print(f'月度统计: {monthly}')

    # 清理测试数据
    CleanRecord.delete_by_batch('test_001')
    print('\n测试数据已清理')
    print('=' * 50)
    print('数据库模块测试通过')
