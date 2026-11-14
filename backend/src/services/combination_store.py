import time

from fastapi import HTTPException
from sqlalchemy import select

from src.models import Combination, CombinationVersion
from src.services import combinations


def _save_version(db, combination, version):
    # Two editors can compute the same next number concurrently. The unique
    # (combination_id, version_no) constraint makes the loser retry instead of
    # silently overwriting a version.
    for attempt in range(4):
        version.version_no = combinations.next_version_no(db, combination.id)
        savepoint = db.begin_nested()
        db.add(version)
        try:
            db.flush()
            savepoint.commit()
        except IntegrityError:
            savepoint.rollback()
            db.expunge(version)
            if attempt == 3:
                raise HTTPException(409, '组合版本正在被其他人修改，请刷新后重试')
            continue
        version.checksum = combinations.checksum_for(version)
        db.flush()
        return version
    raise HTTPException(409, '组合版本正在被其他人修改，请刷新后重试')


def create(db, data, user):
    name = data.name.strip()
    if len(name) < 2:
        raise HTTPException(422, '组合名称去除空格后至少需要两个字符')
    if db.scalar(select(Combination).where(Combination.name == name)):
        raise HTTPException(409, '该组合名称已存在，请修改名称')
    combination = Combination(name=name, created_by=user.id, created_at=time.time())
    db.add(combination)
    db.flush()
    version = combinations.build_version(db, combination, data.dataset_ids, data.resolutions, user.id)
    _save_version(db, combination, version)
    if not version.ready:
        # Do not publish a half-resolved combination: keep the version row for
        # audit but leave it detached until conflicts are resolved.
        combination.current_version_id = None
        db.flush()
        return combination, version, False
    combination.current_version_id = version.id
    db.flush()
    return combination, version, True


def revise(db, combination_id, data, user):
    combination = db.get(Combination, combination_id)
    if not combination:
        raise HTTPException(404, '组合不存在')
    # Lock the combination row so two editors cannot resolve and publish
    # revisions against stale state at the same time.
    db.execute(select(Combination.id).where(Combination.id == combination.id).with_for_update())
    version = combinations.build_version(db, combination, data.dataset_ids, data.resolutions, user.id)
    _save_version(db, combination, version)
    if not version.ready:
        db.flush()
        return combination, version, False
    combination.current_version_id = version.id
    db.flush()
    return combination, version, True


def detail(db, combination_id):
    combination = db.get(Combination, combination_id)
    if not combination:
        raise HTTPException(404, '组合不存在')
    current = (db.get(CombinationVersion, combination.current_version_id)
               if combination.current_version_id else None)
    latest = db.scalar(select(CombinationVersion)
                       .where(CombinationVersion.combination_id == combination_id)
                       .order_by(CombinationVersion.version_no.desc()).limit(1))
    return combination, current, latest


def versions(db, combination_id):
    combination = db.get(Combination, combination_id)
    if not combination:
        raise HTTPException(404, '组合不存在')
    return list(db.scalars(select(CombinationVersion)
                           .where(CombinationVersion.combination_id == combination_id)
                           .order_by(CombinationVersion.version_no.desc())))


def current(db, combination_id):
    combination, version, latest = detail(db, combination_id)
    if latest is None:
        raise HTTPException(409, '该组合尚无样本版本，请先选择批次')
    if version is None or latest.id != version.id:
        # A revision with unresolved conflicts must not be bypassed by silently
        # falling back to the previous publication.
        raise HTTPException(409, '该组合最新版本仍有数值冲突，请选择来源批次并发布后再计算')
    if not version.ready:
        raise HTTPException(409, '该组合仍有数值冲突，请选择来源批次后再计算')
    return combination, version
