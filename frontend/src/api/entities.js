import {api} from './client.js';
export const datasets={list:()=>api('/datasets'),get:id=>api('/datasets/'+id),create:data=>api('/datasets',{method:'POST',body:JSON.stringify(data)})};
export const combinations={list:()=>api('/combinations'),get:id=>api('/combinations/'+id),create:data=>api('/combinations',{method:'POST',body:JSON.stringify(data)}),revise:(id,data)=>api('/combinations/'+id+'/versions',{method:'POST',body:JSON.stringify(data)}),versions:id=>api('/combinations/'+id+'/versions'),version:(id,versionId)=>api('/combinations/'+id+'/versions/'+versionId)};
export const jobs={list:()=>api('/jobs'),get:id=>api('/jobs/'+id),create:data=>api('/jobs',{method:'POST',body:JSON.stringify(data)}),approve:id=>api('/jobs/'+id+'/approve',{method:'POST'})};
export const reports={list:()=>api('/reports'),create:data=>api('/reports',{method:'POST',body:JSON.stringify(data)}),toggle:id=>api('/reports/'+id+'/toggle',{method:'POST'}),deliveries:()=>api('/deliveries')};
