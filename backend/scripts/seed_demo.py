import json
import random
import time

from sqlalchemy import func, select

from migrations.initial import migrate
from src.config.database import Session
from src.models import Audit, Combination, CombinationVersion, Dataset, Delivery, Job, Report, User
from src.services import combinations
from src.services.business import analyze, metadata, seed_records
from src.services.reports import deliver
from src.utils.security import hash_password
from src.utils.serialization import checksum

DEMO_BATCH_NAME = '城西三站 · 整周观察批次'
DEMO_DATES = ['2026-11-09', '2026-11-10', '2026-11-11']
DEMO_COMBINATION = '整周观察组合 · 三站'
DEMO_SUPPLEMENT_BATCH = '补录 · 11 月 9 日下午批次'
DEMO_CONFLICT_COMBINATION = '整周观察组合 · 含补录批次'


def day_records(base, day, offset):
    """Deterministic per-day observations derived from the seeded baseline.

    Each day shifts arrivals/demand a little and drops the final two periods so
    that the end-of-day gap is real: a lag pairing must not reach into the next
    day's first observations.
    """
    rng = random.Random(1003 + offset)
    rows = []
    for record in base:
        if record['period'] >= 94:
            continue
        drift = round(rng.gauss(0, 3), 2)
        rows.append({'station': record['station'], 'period': record['period'],
                     'commute': record['commute'],
                     'arrivals': round(max(0, record['arrivals'] + drift + offset), 2),
                     'demand': round(max(0, record['demand'] - drift * .5 + offset * .4), 2),
                     'observation_date': day})
    return rows


def supplement_records(week_rows):
    """科技园 11-09 afternoon supplement.

    Most rows repeat the week batch exactly (so the resolver must count them
    once); four rows carry different arrivals so the combination surfaces a
    small, reviewable set of conflicts.
    """
    rows = []
    for record in week_rows:
        if record['station'] != '科技园' or record['observation_date'] != DEMO_DATES[0]:
            continue
        if record['period'] < 48:
            continue
        changed = record['period'] in (60, 61, 62, 63)
        rows.append({'station': record['station'], 'period': record['period'],
                     'commute': record['commute'],
                     'arrivals': round(record['arrivals'] + 6, 2) if changed else record['arrivals'],
                     'demand': record['demand'],
                     'observation_date': record['observation_date']})
    return rows


def seed():
    migrate()
    with Session() as db:
        for role, name in [('admin', '林知 · 业务负责人'), ('analyst', '陈舟 · 分析员'), ('viewer', '周禾 · 观察员')]:
            email = role + '@demo.local'
            if not db.scalar(select(User).where(User.email == email)):
                db.add(User(email=email, name=name, role=role, password=hash_password('Demo123!')))
        db.flush()
        admin = db.scalar(select(User).where(User.role == 'admin'))
        analyst = db.scalar(select(User).where(User.role == 'analyst'))
        m = metadata()

        batch = db.scalar(select(Dataset).where(Dataset.name == DEMO_BATCH_NAME))
        if not batch:
            base = seed_records()
            rows = []
            for offset, day in enumerate(DEMO_DATES):
                rows.extend(day_records(base, day, offset))
            batch = Dataset(name=DEMO_BATCH_NAME, source=m['short'] + '-week-202611.csv',
                            records=rows, checksum=checksum(rows), observation_date=DEMO_DATES[-1],
                            created_at=time.time())
            db.add(batch)
            db.flush()

        supplement = db.scalar(select(Dataset).where(Dataset.name == DEMO_SUPPLEMENT_BATCH))
        if not supplement:
            supplement = Dataset(name=DEMO_SUPPLEMENT_BATCH, source=m['short'] + '-supplement-20261109.csv',
                                 records=supplement_records(batch.records), checksum='',
                                 observation_date=DEMO_DATES[0], created_at=time.time())
            supplement.checksum = checksum(supplement.records)
            db.add(supplement)
            db.flush()

        original = db.scalar(select(Dataset).where(Dataset.name == m['dataset_name']))
        if not original:
            rows = seed_records()
            original = Dataset(name=m['dataset_name'], source=m['short'] + '-202611.csv',
                               records=rows, checksum=checksum(rows), observation_date='2026-11-10',
                               created_at=time.time())
            db.add(original)
            db.flush()

        combination = db.scalar(select(Combination).where(Combination.name == DEMO_COMBINATION))
        if not combination:
            combination = Combination(name=DEMO_COMBINATION, created_by=analyst.id, created_at=time.time())
            db.add(combination)
            db.flush()
            version = combinations.build_version(db, combination, [batch.id], {}, analyst.id)
            version.version_no = 1
            db.add(version)
            db.flush()
            version.checksum = combinations.checksum_for(version)
            combination.current_version_id = version.id
            db.flush()
            db.add(Audit(actor=analyst.email, action='combination.create',
                         detail={'id': combination.id, 'version': version.version_no,
                                 'datasets': version.dataset_ids, 'conflicts': 0}, at=time.time()))

        if not db.scalar(select(Job).where(Job.name == '基线复核 · ' + m['name'])):
            params = {p['key']: p['default'] for p in m.get('parameters', [])}
            result = analyze(original.records, params)
            json.dumps(result, ensure_ascii=False, allow_nan=False)
            j = Job(name='基线复核 · ' + m['name'], dataset_id=original.id, params=params,
                    status='completed', result=result, created_by=admin.id,
                    created_at=time.time() - 3600, finished_at=time.time() - 3595, approved=True)
            db.add(j)
            db.flush()
            r = Report(name='每日业务复核简报', job_id=j.id, job_name=j.name,
                       destination='业务复核组 · 本地收件箱', interval_seconds=86400,
                       next_run=time.time() + 86400, enabled=True)
            db.add(r)
            db.flush()
            deliver(db, r)
            db.add(Audit(actor='seed', action='demo.baseline', detail={'dataset': original.id}, at=time.time()))

        conflict_combination = db.scalar(select(Combination).where(Combination.name == DEMO_CONFLICT_COMBINATION))
        if not conflict_combination:
            conflict_combination = Combination(name=DEMO_CONFLICT_COMBINATION, created_by=analyst.id,
                                               created_at=time.time())
            db.add(conflict_combination)
            db.flush()
            version = combinations.build_version(db, conflict_combination, [batch.id, supplement.id], {}, analyst.id)
            version.version_no = 1
            db.add(version)
            db.flush()
            version.checksum = combinations.checksum_for(version)
            db.flush()
            db.add(Audit(actor=analyst.email, action='combination.create',
                         detail={'id': conflict_combination.id, 'version': version.version_no,
                                 'datasets': version.dataset_ids, 'conflicts': len(version.conflicts)},
                         at=time.time()))

        if not db.scalar(select(Job).where(Job.name == '整周观察 · 三站滞后一档')):
            version = db.get(CombinationVersion, combination.current_version_id) if combination.current_version_id else None
            if version and version.ready:
                params = {p['key']: p['default'] for p in m.get('parameters', [])}
                result = analyze(version.samples, params)
                json.dumps(result, ensure_ascii=False, allow_nan=False)
                j = Job(name='整周观察 · 三站滞后一档', dataset_id=None,
                        combination_id=combination.id, combination_name=combination.name,
                        combination_version_id=version.id, combination_version_no=version.version_no,
                        sample_checksum=version.sample_checksum, samples=version.samples,
                        params=params, status='completed', result=result, created_by=analyst.id,
                        created_at=time.time() - 1800, finished_at=time.time() - 1790, approved=False)
                db.add(j)
                db.flush()
                db.add(Audit(actor=analyst.email, action='job.create',
                             detail={'id': j.id, 'params': params, 'combination_id': combination.id,
                                     'combination_version_no': version.version_no,
                                     'sample_checksum': version.sample_checksum}, at=time.time()))

        db.commit()
        counts = {model.__tablename__: db.scalar(select(func.count()).select_from(model))
                  for model in [User, Dataset, Job, Report, Delivery, Audit, Combination, CombinationVersion]}
        print(json.dumps(counts, ensure_ascii=False))
        return counts


if __name__ == '__main__':
    seed()
