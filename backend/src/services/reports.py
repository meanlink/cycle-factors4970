import time, os, csv, io, hashlib, json
from fastapi import HTTPException
from src.models import Job, Report, Delivery
from src.config.settings import ARTIFACT_DIR
def create(db, data):
    j=db.get(Job,data.job_id)
    if not j or j.status!='completed' or not j.approved:
        raise HTTPException(409,'请先选择已完成且获批准的分析结果')
    r=Report(name=data.name, job_id=j.id, job_name=j.name,
             combination_id=j.combination_id, combination_name=j.combination_name,
             combination_version_no=j.combination_version_no, sample_checksum=j.sample_checksum,
             destination=data.destination, interval_seconds=data.interval_seconds,
             next_run=time.time()+data.delay_seconds, enabled=True)
    db.add(r); db.flush()
    return r
def deliver(db, report):
    j=db.get(Job,report.job_id)
    if not j or not j.approved: return
    out=io.StringIO()
    out.write('﻿')
    table=j.result.get('table',{})
    cols=table.get('columns',[])
    writer=csv.writer(out)
    def safe(v):
        if isinstance(v,(int,float)) and not isinstance(v,bool): return v
        text=str(v)
        return "'"+text if text.startswith(('=','+','-','@','\t','\r')) else text
    writer.writerow([safe(c['label']) for c in cols])
    for row in table.get('rows',[]): writer.writerow([safe(row.get(c['key'],'')) for c in cols])
    data=out.getvalue().encode('utf-8')
    delivery=Delivery(report_id=report.id, job_id=j.id, job_name=j.name,
                      combination_id=j.combination_id, combination_name=j.combination_name,
                      combination_version_no=j.combination_version_no,
                      sample_checksum=j.sample_checksum,
                      created_at=time.time(), checksum=hashlib.sha256(data).hexdigest(),
                      filename='', destination=report.destination)
    db.add(delivery); db.flush()
    delivery.filename=f'report-{report.id}-delivery-{delivery.id}.csv'
    os.makedirs(ARTIFACT_DIR,exist_ok=True)
    with open(os.path.join(ARTIFACT_DIR,delivery.filename),'wb') as f:f.write(data)
    with open(os.path.join(ARTIFACT_DIR,delivery.filename+'.json'),'w') as f: json.dump({
        'job':j.name,'job_id':j.id,'params':j.params,'result':j.result,
        'combination':{'id':j.combination_id,'name':j.combination_name,
                       'version_no':j.combination_version_no,'sample_checksum':j.sample_checksum},
        'checksum':delivery.checksum},f,ensure_ascii=False,allow_nan=False)
    report.next_run=time.time()+report.interval_seconds
    return delivery
