import {config} from '../config'
import {getToken,clearSession} from '../stores/session'
import {redirectToLogin} from '../utils/login-return'
import type {StoryCreation,StoryEvent,StorySession} from '../types/story-session'

async function request<T>(path:string,body?:unknown):Promise<T>{
 const token=getToken();if(!token)throw Error('请先登录')
 return new Promise((resolve,reject)=>uni.request({url:config.apiBaseUrl+path,method:body?'POST':'GET',data:body as any,
  header:{Authorization:'Bearer '+token,'Content-Type':'application/json'},timeout:15000,
  success:r=>{if(r.statusCode===401){clearSession();redirectToLogin();reject(Error('登录已过期'));return}
   const v=r.data as any;if(r.statusCode>=300){reject(Object.assign(Error(typeof v.detail==='string'?v.detail:v.message||'操作失败'),{status:r.statusCode}));return}resolve(v.data)},
  fail:()=>reject(Error('连接暂时中断，请重试'))}))
}
export const storySessions={
 list:()=>request<{items:{id:string;title:string;creation:StoryCreation;can_continue:boolean}[]}>('/story-sessions'),
 options:()=>request<{enabled:boolean;images_enabled:boolean;genres:string[];art_styles:string[]}>('/story-options'),
 create:(c:StoryCreation)=>request<StorySession>('/story-sessions',c),
 get:(id:string)=>request<StorySession>('/story-sessions/'+id),
 command:(id:string,c:Record<string,unknown>)=>request<{receipt:{next_creation?:StoryCreation};session:StorySession}>('/story-sessions/'+id+'/commands',c),
 poll:(id:string,seq:number)=>request<{events:StoryEvent[];last_seq:number}>('/story-sessions/'+id+'/events?poll=true&after='+seq),
}

// Stateful parser tolerates UTF-8/chunk boundaries, CRLF, comments and multiple data lines.
export function sseParser(onEvent:(event:StoryEvent)=>void){
 let buffer=''
 return (chunk:string)=>{buffer+=chunk;buffer=buffer.replace(/\r\n/g,'\n');let end:number
  while((end=buffer.indexOf('\n\n'))>=0){const block=buffer.slice(0,end);buffer=buffer.slice(end+2)
   const data=block.split('\n').filter(x=>x.startsWith('data:')).map(x=>x.slice(5).trimStart()).join('\n')
   if(data)onEvent(JSON.parse(data))}}
}

export async function subscribeStories(id:string,after:number,onEvent:(e:StoryEvent)=>void,signal:AbortSignal){
 const token=getToken();if(!token)throw Error('请先登录')
 const response=await fetch(config.apiBaseUrl+'/story-sessions/'+id+'/events?after='+after,
  {headers:{Authorization:'Bearer '+token},signal})
 if(response.status===401){clearSession();redirectToLogin();throw Error('登录已过期')}
 if(!response.ok||!response.body)throw Error('暂时无法订阅进度')
 const reader=response.body.getReader(),decoder=new TextDecoder(),parse=sseParser(onEvent)
 try{while(true){const {done,value}=await reader.read();if(done)break;parse(decoder.decode(value,{stream:true}))}parse(decoder.decode())}
 finally{await reader.cancel().catch(()=>{})}
}

export async function backgroundUrl(id:string,key:string):Promise<string>{
 const response=await fetch(config.apiBaseUrl+'/story-sessions/'+id+'/backgrounds/'+key+'/image',
  {headers:{Authorization:'Bearer '+getToken()}})
 if(!response.ok)throw Error('背景图片暂不可用')
 return URL.createObjectURL(await response.blob())
}
