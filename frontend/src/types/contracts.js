/** @typedef {{id:number,name:string,source:string,rows:number,checksum:string}} Dataset */
/** @typedef {{id:number,name:string,dataset_id:number,combination_id:number,combination_version_no:number,sample_checksum:string,status:string,result:Object,approved:boolean}} AnalysisJob */
/** @typedef {{id:number,name:string,current_version_id:number,current_version:Object}} Combination */
/** @typedef {{id:number,version_no:number,ready:boolean,sample_count:number,sample_checksum:string,conflicts:Array,stats:Object}} CombinationVersion */
/** @typedef {{id:number,name:string,job_id:number,destination:string,next_run:number,enabled:boolean}} ReportSchedule */
export {};
