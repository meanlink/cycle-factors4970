from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from src.config.database import get_db
from src.models import Combination, CombinationVersion
from src.schemas.combination import CombinationInput, CombinationVersionInput
from src.middlewares.auth import current_user, can_write
from src.services import combination_store, combinations
from src.services.audit import record
router=APIRouter(prefix='/combinations')

@router.get('')
def listing(db=Depends(get_db),u=Depends(current_user)):
    rows=[]
    for c in db.scalars(select(Combination).order_by(Combination.id.desc())):
        v=db.get(CombinationVersion,c.current_version_id) if c.current_version_id else None
        latest=db.scalar(select(CombinationVersion)
                         .where(CombinationVersion.combination_id==c.id)
                         .order_by(CombinationVersion.version_no.desc()).limit(1))
        rows.append(combinations.combination_dict(c,v,latest))
    return rows

def _detail_payload(db,combination_id,published=None):
    combination,current,latest=combination_store.detail(db,combination_id)
    data=combinations.combination_dict(combination,current,latest)
    if published is not None: data['published']=published
    return {**data,
            'current_version':combinations.version_summary(current) if current else None,
            'latest_version':combinations.version_detail(latest) if latest else None}

@router.post('',status_code=201)
def create(data:CombinationInput,db=Depends(get_db),u=Depends(can_write)):
    c,v,published=combination_store.create(db,data,u)
    record(db,u.email,'combination.create',{'id':c.id,'version':v.version_no,'published':published,
                                            'datasets':v.dataset_ids,'conflicts':len(v.conflicts)})
    db.commit()
    return _detail_payload(db,c.id,published)

@router.get('/{id}')
def detail(id:int,db=Depends(get_db),u=Depends(current_user)):
    return _detail_payload(db,id)

@router.post('/{id}/versions',status_code=201)
def revise(id:int,data:CombinationVersionInput,db=Depends(get_db),u=Depends(can_write)):
    c,v,published=combination_store.revise(db,id,data,u)
    stale=v.stats.get('stale_resolutions',[])
    record(db,u.email,'combination.revise',{'id':c.id,'version':v.version_no,'published':published,
                                            'datasets':v.dataset_ids,'conflicts':len(v.conflicts),
                                            'stale_count':len(stale),
                                            'stale_keys':[x['key'] for x in stale[:20]]})
    db.commit()
    return _detail_payload(db,c.id,published)

@router.get('/{id}/versions')
def version_list(id:int,db=Depends(get_db),u=Depends(current_user)):
    return [combinations.version_summary(v) for v in combination_store.versions(db,id)]

@router.get('/{id}/versions/{version_id}')
def version_detail(id:int,version_id:int,db=Depends(get_db),u=Depends(current_user)):
    v=db.get(CombinationVersion,version_id)
    if not v or v.combination_id!=id: raise HTTPException(404,'组合版本不存在')
    return combinations.version_detail(v,sample_limit=2000)
