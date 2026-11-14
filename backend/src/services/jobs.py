import time
from fastapi import HTTPException
from redis import Redis
from src.config.settings import REDIS_URL
from src.models import Dataset, Job
from src.services import combination_store
from src.services.business import metadata


def _validate_params(data):
    allowed={p['key']:p for p in metadata().get('parameters',[])}
    if set(data.params)-set(allowed): raise HTTPException(422,'包含未知分析参数')
    params={k:p['default'] for k,p in allowed.items()}
    params.update(data.params)
    for key,p in allowed.items():
        v=params[key]
        if p['type']=='number':
            try:
                v=float(v)
                if not (p.get('min',-1e9)<=v<=p.get('max',1e9)): raise ValueError()
                params[key]=v
            except (ValueError,TypeError): raise HTTPException(422, f'{p["label"]} 超出范围或非数值')
        elif str(v) not in [str(o['value']) for o in p.get('options',[])]:
            raise HTTPException(422,f'{p["label"]} 不是有效选项')
    return params


def create(db, data, user):
    params=_validate_params(data)
    if data.combination_id is not None:
        if data.dataset_id is not None:
            raise HTTPException(422,'单批次与组合只能选择一个作为分析输入')
        combination,version=combination_store.current(db,data.combination_id)
        # Snapshot the *resolved* current version. The version row is immutable,
        # so even if someone revises the combination while this job is queued,
        # the worker sees exactly the samples the researcher submitted against.
        samples=version.samples
        if not samples:
            raise HTTPException(409,'该组合版本没有可用样本')
        j=Job(name=data.name, dataset_id=None, combination_id=combination.id,
              combination_name=combination.name, combination_version_id=version.id,
              combination_version_no=version.version_no, sample_checksum=version.sample_checksum,
              samples=samples, params=params, created_by=user.id, created_at=time.time(), status='queued')
    else:
        if data.dataset_id is None:
            raise HTTPException(422,'请选择数据批次或按日期组合')
        if not db.get(Dataset,data.dataset_id): raise HTTPException(404,'数据批次不存在')
        j=Job(name=data.name, dataset_id=data.dataset_id, params=params, created_by=user.id, created_at=time.time(), status='queued')
    db.add(j); db.flush()
    return j


def enqueue(job_id):
    try:
        r=Redis.from_url(REDIS_URL); r.rpush('analysis:queue',job_id); r.close()
    except Exception:
        pass # SQL queued status is the durable fallback
