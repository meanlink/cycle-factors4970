"""按日期组合批次：缺口不跨日配对、同键去重、数值冲突须选来源。"""
import hashlib
import json
import time
from datetime import date, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models import Combination, CombinationVersion, Dataset
from src.utils.serialization import checksum

VALUE_FIELDS = ('commute', 'arrivals', 'demand')
SAMPLE_FIELDS = ('station', 'observation_date', 'period', 'commute', 'arrivals', 'demand')


def normalize_date(value):
    """Accept ``YYYY-MM-DD`` / ISO timestamps; return ``''`` when unusable."""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value or '').strip()
    if not text:
        return ''
    if 'T' in text:
        text = text.split('T', 1)[0]
    elif ' ' in text:
        text = text.split(' ', 1)[0]
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError:
        return ''


def row_date(row, dataset):
    return normalize_date(row.get('observation_date')) or (dataset.observation_date or '')


def sample_key(row):
    try:
        period = float(row['period'])
    except (KeyError, TypeError, ValueError):
        period = float('inf')
    return (str(row['station']), normalize_date(row.get('observation_date')), period, str(row.get('period')))


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)


def _values(row):
    return {field: row.get(field) for field in VALUE_FIELDS}


def sample_checksum(rows):
    """Order-independent fingerprint of a resolved sample."""
    ordered = sorted(({k: r.get(k) for k in SAMPLE_FIELDS} for r in rows), key=sample_key)
    return hashlib.sha256(_canonical(ordered).encode()).hexdigest()


def _signature(candidates):
    """Fingerprint the *distinct values* at one key.

    Adding another copy of an already-present value does not change the shape
    of the conflict; introducing a new value does, which invalidates any earlier
    choice made against the old candidate set.
    """
    values = sorted({_canonical(_values(c['row'])) for c in candidates})
    return hashlib.sha256(_canonical(values).encode()).hexdigest()[:32]


def dataset_summary(d):
    return {'id': d.id, 'name': d.name, 'checksum': d.checksum,
            'observation_date': d.observation_date or '', 'rows': len(d.records)}


def combination_dict(c, version=None, latest=None):
    data = {'id': c.id, 'name': c.name, 'created_at': c.created_at,
            'current_version_id': c.current_version_id,
            'published': bool(version and (latest is None or latest.id == version.id)),
            'unpublished_conflicts': bool(latest and version and latest.id != version.id)}
    if version is not None:
        data['current_version'] = version_summary(version)
    if latest is not None:
        data['latest_version_no'] = latest.version_no
        data['latest_ready'] = latest.ready
        data['latest_conflict_count'] = len(latest.conflicts or [])
    return data


def version_summary(v):
    stats = v.stats or {}
    return {'id': v.id, 'combination_id': v.combination_id, 'version_no': v.version_no,
            'created_at': v.created_at, 'dataset_ids': v.dataset_ids,
            'dataset_meta': v.dataset_meta, 'resolutions': v.resolutions,
            'conflicts_top': (v.conflicts or [])[:3],
            'conflict_count': len(v.conflicts or []),
            'resolved_count': stats.get('resolved_conflict_keys', 0),
            'ready': v.ready, 'sample_count': len(v.samples or []),
            'sample_checksum': v.sample_checksum, 'checksum': v.checksum,
            'stats': stats, 'stale_resolutions': stats.get('stale_resolutions', []),
            'dropped_resolutions': stats.get('dropped_resolutions', [])}


def version_detail(v, sample_limit=200):
    return {**version_summary(v), 'conflicts': v.conflicts or [],
            'samples': (v.samples or [])[:sample_limit]}


def _load_datasets(db, dataset_ids):
    if not dataset_ids:
        raise HTTPException(422, '请至少选择一个数据批次')
    unique, seen = [], set()
    for raw in dataset_ids:
        try:
            dataset_id = int(raw)
        except (TypeError, ValueError):
            raise HTTPException(422, '数据批次编号无效')
        if dataset_id in seen:
            raise HTTPException(422, '同一批次不能重复加入组合')
        seen.add(dataset_id)
        unique.append(dataset_id)
    datasets = {d.id: d for d in db.scalars(select(Dataset).where(Dataset.id.in_(unique)))}
    missing = [str(i) for i in unique if i not in datasets]
    if missing:
        raise HTTPException(404, '数据批次不存在：' + '、'.join(missing))
    return [datasets[i] for i in unique]


def _collect(datasets):
    """Group rows by (station, date, period), keeping every source batch."""
    elements, input_rows = {}, 0
    for dataset in datasets:
        for row in dataset.records:
            input_rows += 1
            try:
                station = str(row['station'])
                period = row['period']
                float(period)
                values = {field: float(row[field]) for field in VALUE_FIELDS}
            except (KeyError, TypeError, ValueError):
                raise HTTPException(422, f'批次「{dataset.name}」含不完整观测')
            observation_date = row_date(row, dataset)
            if not observation_date:
                raise HTTPException(422, f'批次「{dataset.name}」缺少观测日期，无法按日期组合')
            # Periods may arrive as 12 or "12"; they identify the same slot.
            key = (station, observation_date, float(period))
            elements.setdefault(key, {'key': tuple(str(part) for part in key), 'station': station,
                                      'observation_date': observation_date,
                                      'period': period, 'candidates': []})['candidates'].append({
                'dataset_id': dataset.id, 'dataset_name': dataset.name,
                'dataset_checksum': dataset.checksum,
                'row': {**values, 'station': station, 'observation_date': observation_date,
                        'period': period}})
    return elements, input_rows


def _candidate(c):
    return {'dataset_id': c['dataset_id'], 'dataset_name': c['dataset_name'],
            'dataset_checksum': c['dataset_checksum'],
            'commute': c['row']['commute'], 'arrivals': c['row']['arrivals'],
            'demand': c['row']['demand']}


def _conflict(element, candidates):
    groups = {}
    for candidate in candidates:
        groups.setdefault(_canonical(_values(candidate['row'])), []).append(candidate)
    group_list = list(groups.values())
    pairs = []
    for i, left_group in enumerate(group_list):
        for right_group in group_list[i + 1:]:
            left, right = left_group[0], right_group[0]
            pairs.append({'left': _candidate(left), 'right': _candidate(right),
                          'differences': [field for field in VALUE_FIELDS
                                          if left['row'][field] != right['row'][field]]})
    return {'key': '|'.join(element['key']), 'station': element['station'],
            'observation_date': element['observation_date'], 'period': element['period'],
            'candidates': [_candidate(c) for c in candidates], 'pairs': pairs,
            'signature': _signature(candidates)}


def _sample(chosen, sources):
    return {**chosen['row'], 'source_dataset_id': chosen['dataset_id'],
            'source_dataset_name': chosen['dataset_name'],
            'source_dataset_ids': [s[0] for s in sources],
            'source_dataset_names': [s[1] for s in sources]}


def _apply(candidates, resolutions, element, stale):
    """Resolve one key.

    Returns ``(sample, conflict, resolved_record)``. A resolution is keyed by the
    (station, date, period) key *and* the conflict signature it was made
    against. When the candidate values change, the old choice is reported as
    stale and is never applied to the new conflict — even when it happens to
    name a batch that is still present.
    """
    groups = {}
    for candidate in candidates:
        groups.setdefault(_canonical(_values(candidate['row'])), []).append(candidate)
    sources = sorted({(c['dataset_id'], c['dataset_name']) for c in candidates})
    if len(groups) == 1:
        # Identical observation repeated across batches: keep one copy from the
        # lowest batch id so the result is stable regardless of selection order.
        chosen = sorted(groups.popitem()[1], key=lambda c: c['dataset_id'])[0]
        return _sample(chosen, sources), None, None

    conflict = _conflict(element, candidates)
    if conflict['key'] not in resolutions:
        return None, conflict, None
    raw = resolutions[conflict['key']]
    if not isinstance(raw, dict):
        # A bare dataset id carries no conflict identity, so it cannot prove it
        # was chosen for *this* conflict. Treat it as stale rather than guess.
        stale.append({'key': conflict['key'], 'dataset_id': None, 'reason': 'missing_signature',
                      'signature': conflict['signature']})
        return None, conflict, None
    dataset_id, signature = raw.get('dataset_id'), raw.get('signature')
    if signature != conflict['signature']:
        # Report the live conflict shape so the editor can re-pick immediately.
        stale.append({'key': conflict['key'], 'dataset_id': dataset_id,
                      'signature': conflict['signature'], 'previous_signature': signature,
                      'reason': 'signature_changed'})
        return None, conflict, None
    try:
        dataset_id = int(dataset_id)
    except (TypeError, ValueError):
        stale.append({'key': conflict['key'], 'dataset_id': dataset_id,
                      'signature': conflict['signature'], 'reason': 'invalid_source'})
        return None, conflict, None
    matching = [c for c in candidates if c['dataset_id'] == dataset_id]
    if not matching:
        stale.append({'key': conflict['key'], 'dataset_id': dataset_id,
                      'signature': conflict['signature'], 'reason': 'source_removed'})
        return None, conflict, None
    chosen_sources = sorted({(c['dataset_id'], c['dataset_name']) for c in matching})
    record = {'key': conflict['key'], 'station': conflict['station'],
              'observation_date': conflict['observation_date'], 'period': conflict['period'],
              'chosen_dataset_id': dataset_id,
              'chosen_dataset_name': matching[0]['dataset_name'],
              'signature': conflict['signature'], 'pairs': conflict['pairs'],
              'candidates': conflict['candidates']}
    return _sample(matching[0], chosen_sources), None, record


def _sort_key(row):
    try:
        period = float(row['period'])
    except (TypeError, ValueError):
        period = float('inf')
    return (str(row['station']), normalize_date(row.get('observation_date')), period, str(row['period']))


def build_version(db: Session, combination: Combination, dataset_ids, resolutions,
                  created_by, created_at=None):
    """Resolve a batch set into a new immutable version (not yet persisted)."""
    datasets = _load_datasets(db, dataset_ids)
    resolutions = {str(k): v for k, v in (resolutions or {}).items()}
    elements, input_rows = _collect(datasets)
    stale, samples, conflicts, resolved = [], [], [], []
    effective = {}
    for key in sorted(elements):
        sample, conflict, record = _apply(elements[key]['candidates'], resolutions,
                                          elements[key], stale)
        if conflict is not None:
            conflicts.append(conflict)
        else:
            samples.append(sample)
        if record is not None:
            resolved.append(record)
            effective[record['key']] = resolutions[record['key']]
    samples.sort(key=_sort_key)
    stale_keys = {item['key'] for item in stale}
    dropped = sorted(set(resolutions) - set(effective) - stale_keys)

    per_date, stations = {}, set()
    for sample in samples:
        stations.add(sample['station'])
        bucket = per_date.setdefault(sample['observation_date'],
                                     {'date': sample['observation_date'], 'rows': 0, 'datasets': set()})
        bucket['rows'] += 1
        bucket['datasets'].update(sample['source_dataset_ids'])
    dates = sorted(per_date)
    conflict_keys = {c['key'] for c in conflicts}
    collapsed_rows = sum(max(0, len(element['candidates']) - 1) for element in elements.values()
                         if element['key'] not in conflict_keys)
    conflict_rows = sum(len(element['candidates']) for element in elements.values()
                        if element['key'] in conflict_keys)
    stats = {
        'input_rows': input_rows,
        'unique_keys': len(elements),
        'unique_samples': len(samples),
        'collapsed_rows': collapsed_rows,
        'conflict_rows': conflict_rows,
        'conflict_keys': len(conflicts),
        'resolved_conflict_keys': len(resolved),
        'stations': sorted(stations),
        'dates': dates,
        'per_date': [{'date': d, 'rows': per_date[d]['rows'],
                      'dataset_ids': sorted(per_date[d]['datasets'])} for d in dates],
        'stale_resolutions': stale,
        'dropped_resolutions': dropped,
    }
    version = CombinationVersion(
        combination_id=combination.id, version_no=0, created_by=created_by,
        created_at=created_at or time.time(), dataset_ids=[d.id for d in datasets],
        dataset_meta=[dataset_summary(d) for d in datasets],
        resolutions=effective, conflicts=conflicts, samples=samples, stats=stats,
        ready=not conflicts and bool(samples),
        sample_checksum=sample_checksum(samples), checksum='')
    return version


def checksum_for(version):
    return checksum({'combination_id': version.combination_id, 'version_no': version.version_no,
                     'dataset_ids': version.dataset_ids, 'resolutions': version.resolutions,
                     'sample_checksum': version.sample_checksum,
                     'conflicts': version.conflicts, 'ready': version.ready})


def next_version_no(db, combination_id):
    numbers = db.scalars(select(CombinationVersion.version_no)
                         .where(CombinationVersion.combination_id == combination_id))
    return max(numbers, default=0) + 1
