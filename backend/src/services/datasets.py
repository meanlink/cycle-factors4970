from fastapi import HTTPException
from sqlalchemy import select
from src.models import Dataset
from src.services.business import metadata
from src.services.combinations import normalize_date
from src.utils.serialization import checksum
import math, time
def create(db, data):
    name=data.name.strip()
    if len(name)<2: raise HTTPException(422, '批次名称去除空格后至少需要两个字符')
    if db.scalar(select(Dataset).where(Dataset.name==name)):
        raise HTTPException(409, '该数据批次名已存在，请修改名称')
    observation_date=normalize_date(data.observation_date)
    if data.observation_date and not observation_date:
        raise HTTPException(422, '批次观测日期须为 YYYY-MM-DD')
    for index,row in enumerate(data.records):
        for c in metadata()['columns']:
            value=row.get(c['key'])
            if value is None or value=='': raise HTTPException(422, f'第 {index+1} 行缺少字段 {c["label"]}')
            if c['type']=='number':
                try:
                    if isinstance(value,bool) or not math.isfinite(float(value)): raise ValueError()
                    row[c['key']]=float(value)
                except (TypeError, ValueError, OverflowError): raise HTTPException(422, f'第 {index+1} 行 {c["label"]} 必须为有限数值')
        if row.get('observation_date'):
            day=normalize_date(row['observation_date'])
            if not day:
                raise HTTPException(422, f'第 {index+1} 行观测日期须为 YYYY-MM-DD')
            row['observation_date']=day
        elif observation_date:
            row['observation_date']=observation_date
        else:
            raise HTTPException(422, f'第 {index+1} 行缺少观测日期，无法按日期组合；请为批次或每行提供 observation_date')
    # The batch-level date is the explicit fallback for rows that omitted one.
    d=Dataset(name=name, source=data.source, records=data.records, checksum=checksum(data.records),
              observation_date=observation_date, created_at=time.time())
    db.add(d); db.flush()
    return d
