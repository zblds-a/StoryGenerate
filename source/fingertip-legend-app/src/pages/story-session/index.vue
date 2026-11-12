<script setup lang="ts">
import {ref,computed} from 'vue'
import {onLoad,onShow,onHide,onUnload} from '@dcloudio/uni-app'
import FeatureLayout from '../../components/FeatureLayout.vue'
import {api} from '../../services/api'
import {storySessions,subscribeStories,backgroundUrl} from '../../services/story-sessions'
import type {StoryCreation,StorySession,StoryEvent} from '../../types/story-session'
import type {Character} from '../../types/domain'
import {sessionState} from '../../stores/session'
import {requireSession,errorMessage} from '../../utils/navigation'
import {requestKey} from '../../utils/production'

const state=ref<StorySession>(),roles=ref<Character[]>([]),error=ref(''),busy=ref(false),advanced=ref(false),text=ref('')
const existing=ref<{id:string;title:string;creation:StoryCreation;can_continue:boolean}[]>([])
const options=ref<{enabled:boolean;images_enabled:boolean;genres:string[];art_styles:string[]}>()
const creation=ref<StoryCreation>({idempotency_key:requestKey(),form:'short',method:'assist',idea:'',genre:'国风奇幻',feeling:'warm',ending:'happy',series_ending:'open',art_style:'guofeng',series_episodes:6,character_ids:[],output:'script',casting:null})
const showBackground=ref<Record<string,boolean>>({})
const changeScope=ref<'scene'|'following'>('following'), targetScene=ref('')
const canCreate=computed(()=>!!options.value?.enabled&&creation.value.character_ids.length>0&&creation.value.character_ids.length<=6&&(creation.value.method!=='idea'||!!creation.value.idea.trim())&&(creation.value.method!=='continue'||!!creation.value.source_session_id))
const stages:Record<string,string>={directions:'正在帮你构思',directions_ready:'选择一个故事方向',outlining:'正在构思大纲',outline_ready:'确认故事走向',writing:'正在创作剧本',change_ready:'确认调整范围',script_ready:'剧本已完成，等待你确认',media_pending:'正在提交声音制作',media_ready:'已进入作品制作',confirmed:'剧本已确认',failed:'本次生成已暂停',cancelled:'已取消'}
const failures:Record<string,string>={EXTERNAL_RESULT_UNKNOWN:'供应商调用结果尚待核对，已暂停后续调用，请联系服务维护人员。',DURATION_BUDGET_EXHAUSTED:'前面的篇幅已超出本集预算，可以从较早一幕调整，再继续创作。',EPISODE_DURATION_OUT_OF_RANGE:'本集篇幅暂未达标，可以调整受影响的场景后继续。',UNAPPROVED_ROLE:'出现了未选择的发声角色，已停止交付，可以调整方向后重试。',WORKER_RESULT_UNKNOWN:'调用结果尚待核对，生成已暂停，请联系服务维护人员。',GENERATION_FAILED:'这一阶段暂未完成，可以重试，或调整故事方向。',CALL_BUDGET_EXCEEDED:'本次创作已达到调用预算，请保存当前内容后联系服务维护人员。'}
const can=(action:string)=>!!state.value?.available_actions.includes(action)
const previews=ref<Record<string,{attempt:string;text:string}>>({}),images=ref<Record<string,string>>({}),imageHashes=ref<Record<string,string>>({})
let active=true,controller:AbortController|undefined,timer:ReturnType<typeof setTimeout>|undefined,seq=0,epoch=0,refreshing=false
const cache=()=> 'story-session:'+sessionState.session?.user.id
async function refresh(){if(!state.value||refreshing)return;refreshing=true;const id=state.value.id,token=epoch
 try{const value=await storySessions.get(id);if(token===epoch){if(value.generation_epoch!==state.value?.generation_epoch)previews.value={};state.value=value;await loadImages()}}
 catch(e){if(token===epoch)error.value=errorMessage(e)}finally{refreshing=false}}
async function loadImages(){if(typeof window==='undefined'||!state.value)return
 for(const [key,bg] of Object.entries(state.value.backgrounds)){if(bg.status!=='ready'){if(images.value[key]){URL.revokeObjectURL(images.value[key]);delete images.value[key];delete imageHashes.value[key]}continue}
  const hash=bg.image?.sha256;if(imageHashes.value[key]===hash&&images.value[key])continue
  const id:string=state.value.id;const url:string=await backgroundUrl(id,key);if(state.value?.id!==id||state.value.backgrounds[key]?.status!=='ready'||state.value.backgrounds[key]?.image?.sha256!==hash){URL.revokeObjectURL(url);continue}
  if(images.value[key])URL.revokeObjectURL(images.value[key]);images.value[key]=url;imageHashes.value[key]=hash||''}}
function event(e:StoryEvent){if(!state.value||e.session_id!==state.value.id||e.seq<=seq)return;seq=e.seq
 if(e.generation_epoch<state.value.generation_epoch)return
 if(e.type==='outline.delta'||e.type==='scene.text.delta'){const key=e.payload.scene_key||'outline';const old=previews.value[key]
  previews.value[key]={attempt:e.payload.attempt_id,text:(old?.attempt===e.payload.attempt_id?old.text+'\n':'')+e.payload.text}}
 else{if(e.type==='scene.ready')delete previews.value[e.payload.scene_key];if(e.type==='outline.ready')delete previews.value.outline;void refresh()}}
async function listen(){if(!active||!state.value)return;controller=new AbortController()
 try{if(typeof window!=='undefined'&&typeof fetch!=='undefined')await subscribeStories(state.value.id,seq,event,controller.signal)
  else{const batch=await storySessions.poll(state.value.id,seq);batch.events.forEach(event)}}
 catch(e){if(!controller.signal.aborted)error.value='进度连接暂时中断，正在重新连接；生成会继续。'}
 finally{if(active)timer=setTimeout(async()=>{await refresh();void listen()},1500)}}
function stop(){active=false;epoch++;controller?.abort();clearTimeout(timer)}
function resume(){active=true;if(state.value){void refresh();void listen()}}
onLoad(async q=>{if(!requireSession())return
 try{options.value=await storySessions.options();if(!options.value.enabled)return;roles.value=await api.characters();existing.value=(await storySessions.list()).items
  const id=String(q?.id||uni.getStorageSync(cache())||'');if(id){state.value=await storySessions.get(id);seq=state.value.last_seq;await loadImages();void listen()}}
 catch(e){error.value=errorMessage(e)}})
onShow(()=>{if(!active)resume()});onHide(stop);onUnload(()=>{stop();Object.values(images.value).forEach(v=>URL.revokeObjectURL(v))})
function toggle(id:string){const ids=creation.value.character_ids;creation.value.character_ids=ids.includes(id)?ids.filter(x=>x!==id):[...ids,id]}
async function create(){if(busy.value)return;busy.value=true;error.value=''
 try{creation.value.output='script';creation.value.casting=null
  const body={...creation.value,source_session_id:creation.value.method==='continue'?creation.value.source_session_id:undefined}
  const signature=JSON.stringify({...body,idempotency_key:undefined}),key=cache()+':creation',pending=uni.getStorageSync(key)
  body.idempotency_key=pending?.signature===signature?pending.key:requestKey();uni.setStorageSync(key,{signature,key:body.idempotency_key})
  state.value=await storySessions.create(body);uni.removeStorageSync(key);uni.setStorageSync(cache(),state.value.id);seq=0;void listen()}
 catch(e){error.value=errorMessage(e)}finally{busy.value=false}}
async function command(kind:string,extra:Record<string,unknown>={}){if(!state.value||busy.value)return;busy.value=true;error.value=''
 try{const current=state.value
  const payload={kind,...extra};const cacheKey=cache()+':command',signature=JSON.stringify([current.id,payload]),pending=uni.getStorageSync(cacheKey)
  const value=pending?.signature===signature?pending.value:{...payload,command_id:requestKey(),expected_revision:current.revision}
  uni.setStorageSync(cacheKey,{signature,value});let result
  try{result=await storySessions.command(current.id,value)}catch(e){
   if((e as any).status!==409||(e as Error).message!=='REVISION_CONFLICT'||!['change','revise_outline','cancel'].includes(kind))throw e
   const latest=await storySessions.get(current.id);state.value=latest
   if(!latest.available_actions.includes(kind))throw e
   const retry={...value,command_id:requestKey(),expected_revision:latest.revision}
   uni.setStorageSync(cacheKey,{signature,value:retry});result=await storySessions.command(current.id,retry)
  }
  uni.removeStorageSync(cacheKey);state.value=result.session
  if(result.receipt.next_creation){state.value=await storySessions.create(result.receipt.next_creation);targetScene.value='';uni.setStorageSync(cache(),state.value.id);stop();seq=0;resume()}
  await loadImages();text.value=''
 }catch(e){if((e as any).status===409){uni.removeStorageSync(cache()+':command');await refresh();error.value='内容已有更新，请核对后再次选择。'}else error.value=errorMessage(e)}finally{busy.value=false}}
function change(option?:string,key=targetScene.value||undefined,scope=changeScope.value){void command(can('revise_outline')?'revise_outline':'change',{option_id:option||null,target_id:key||null,text:text.value,scope})}
async function confirmChange(){if(!state.value?.pending_change)return
 // Server hashes canonical JSON; retrieve the exact proposed fingerprint from events/snapshot.
 const s=state.value;await command('confirm_change',{fingerprint:(s as any).pending_change_fingerprint})}
function download(key:string){if(!images.value[key])return;const a=document.createElement('a');a.href=images.value[key];a.download=key+'.png';a.click()}
function clearImages(){Object.values(images.value).forEach(v=>URL.revokeObjectURL(v));images.value={};imageHashes.value={}}
async function openStory(id:string){stop();clearImages();targetScene.value='';previews.value={};state.value=await storySessions.get(id);uni.setStorageSync(cache(),id);seq=state.value.last_seq;await loadImages();resume()}
async function exportStory(){if(!state.value)return;const data=await storySessions.export(state.value.id);const body=JSON.stringify(data,null,2);if(typeof document==='undefined'){uni.setClipboardData({data:body});return}const url=URL.createObjectURL(new Blob([body],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='story-'+state.value.id+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
function speaker(id?:string){return roles.value.find(r=>r.id===id)?.name||'旁白'}
function fresh(){stop();clearImages();targetScene.value='';state.value=undefined;uni.removeStorageSync(cache());previews.value={};creation.value.idempotency_key=requestKey();active=true;storySessions.list().then(v=>existing.value=v.items).catch(()=>{})}
</script>
<template><FeatureLayout title="一起创作故事" subtitle="选一个方向，让故事与你一起生长" active="create"><view class="page-content">
<text v-if="error" class="error-copy" role="alert">{{error}}</text>
<view v-if="options&&!options.enabled" class="paper-panel">协助创作尚未启用，可继续使用原创作入口。</view>
<view v-else-if="!state" class="paper-panel">
 <text class="section-title serif">你想怎样开始？</text><view v-if="existing.length" class="spaced"><text class="field-label">最近的故事 · 可继续阅读或修改</text><button v-for="old in existing.slice(0,8)" :key="old.id" class="chip" @tap="openStory(old.id)">{{old.title}}</button></view>
 <view class="chip-list spaced"><button class="chip" :class="{selected:creation.form==='short'}" @tap="creation.form='short'">短剧·完整一篇</button><button class="chip" :class="{selected:creation.form==='series'}" @tap="creation.form='series'">长剧·先写首集</button></view>
 <view v-if="creation.form==='series'"><text class="field-label">计划集数</text><picker :range="[3,6,12,24]" @change="creation.series_episodes=[3,6,12,24][Number($event.detail.value)]"><view class="form-input">{{creation.series_episodes}} 集</view></picker></view>
 <view class="chip-list spaced"><button class="chip" :class="{selected:creation.method==='assist'}" @tap="creation.method='assist'">帮我构思</button><button class="chip" :class="{selected:creation.method==='idea'}" @tap="creation.method='idea'">我有一个灵感</button><button class="chip" :class="{selected:creation.method==='continue'}" @tap="creation.method='continue'">续写已有故事</button></view><view v-if="creation.method==='continue'"><button v-for="old in existing.filter(s=>s.can_continue)" :key="old.id" class="chip" :class="{selected:creation.source_session_id===old.id}" @tap="creation.source_session_id=old.id;creation.character_ids=[...old.creation.character_ids];creation.form='series';creation.series_episodes=old.creation.series_episodes">{{old.title}}</button><text class="small-note">选择已确认的长剧继续下一集。</text></view>
 <textarea v-if="creation.method==='idea'" v-model="creation.idea" class="form-textarea spaced" maxlength="2000" placeholder="一句灵感就够了"/>
 <text class="field-label">参与角色（最多 6 位）</text><view class="chip-list"><button v-for="role in roles" :key="role.id" class="chip" :class="{selected:creation.character_ids.includes(role.id)}" :disabled="busy||creation.method==='continue'||(creation.character_ids.length>=6&&!creation.character_ids.includes(role.id))" @tap="toggle(role.id)">{{role.name}}</button></view>
 <button class="text-link spaced" @tap="advanced=!advanced">{{advanced?'收起偏好':'题材、结局与美术偏好'}}</button>
 <view v-if="advanced"><text class="field-label">题材</text><view class="chip-list"><button v-for="genre in options?.genres" :key="genre" class="chip" :class="{selected:creation.genre===genre}" @tap="creation.genre=genre">{{genre}}</button></view>
 <text class="field-label">故事感觉</text><view class="chip-list"><button v-for="item in [{id:'warm',name:'温暖'},{id:'light',name:'轻松'},{id:'tense',name:'紧张'},{id:'fantastic',name:'奇幻'}]" :key="item.id" class="chip" :class="{selected:creation.feeling===item.id}" @tap="creation.feeling=item.id">{{item.name}}</button></view>
 <text class="field-label">{{creation.form==='series'?'本集收束':'结局'}}</text><view class="chip-list"><button v-for="item in [{id:'happy',name:'圆满'},{id:'open',name:'开放'},{id:'cliffhanger',name:'悬念'}]" :key="item.id" class="chip" :class="{selected:creation.ending===item.id}" @tap="creation.ending=item.id">{{item.name}}</button></view>
 <template v-if="creation.form==='series'"><text class="field-label">系列最终走向</text><view class="chip-list"><button v-for="item in [{id:'happy',name:'最终圆满'},{id:'open',name:'开放主线'},{id:'cliffhanger',name:'留下悬念'}]" :key="item.id" class="chip" :class="{selected:creation.series_ending===item.id}" @tap="creation.series_ending=item.id">{{item.name}}</button></view></template>
 <text class="field-label">纯场景背景风格</text><view class="chip-list"><button v-for="item in [{id:'guofeng',name:'国风'},{id:'watercolor',name:'水彩'},{id:'animation',name:'动画'}]" :key="item.id" class="chip" :class="{selected:creation.art_style===item.id}" @tap="creation.art_style=item.id">{{item.name}}</button></view>
</view>
 <text class="small-note spaced">{{options?.images_enabled?'每幕背景图将并行生成，供预览和下载。':'背景生图未启用，仍会提供各幕提示词。'}}</text>
 <button class="warm-button full-button" :disabled="busy||!canCreate" @tap="create">开始一起创作</button>
</view>
<template v-else><view class="paper-panel"><text class="section-title serif">{{stages[state.stage]||state.stage}}</text><text class="small-note spaced">第 {{state.episode_number}} 集 · 已完成 {{state.scenes.length}} / {{state.scene_keys.length}} 幕</text>
 <text v-if="state.pending_change" class="small-note spaced">已收到调整：{{state.pending_change.instructions.join('；')}}。{{state.stage==='change_ready'?'等待你确认影响范围。':'将在场景边界处理。'}}</text>
 <text v-if="state.error_code" class="error-copy spaced">{{failures[state.error_code]||'这一阶段暂未完成，已保留生成内容。'}}</text>
 <button v-if="can('cancel')" class="outline-button full-button" :disabled="busy" @tap="command('cancel')">取消生成</button>
 <button v-if="can('retry')" class="outline-button full-button" :disabled="busy" @tap="command('retry')">重试当前阶段</button></view>
 <view v-if="can('select_direction')" class="paper-panel section-gap"><button v-for="d in state.directions" :key="d.id" class="direction" :disabled="busy" @tap="command('select_direction',{target_id:d.id})"><text class="field-label">{{d.title}}</text><text>{{d.premise}}</text></button></view>
 <view v-if="previews.outline" class="paper-panel section-gap"><text class="small-note">大纲构思中 · 待完成后确认</text><text class="copy">{{previews.outline.text}}</text></view>
 <view v-if="state.outline" class="paper-panel section-gap"><text class="section-title serif">{{state.outline.title}}</text><text class="copy">{{state.outline.premise}}</text><text v-for="relation in state.outline.relationships" :key="relation" class="copy">{{relation}}</text>
 <template v-if="state.creation.form==='series'"><text class="copy">系列主线：{{state.outline.series_arc}}</text><text v-for="(summary,i) in state.outline.episode_summaries" :key="i" class="copy">第{{i+1}}集：{{summary}}</text></template>
 <text v-for="(scene,i) in state.outline.scenes" :key="i" class="copy">第{{i+1}}幕 · {{scene.title}}：{{scene.goal}}</text>
 <view v-if="can('set_preferences')" class="spaced"><text class="field-label">调整结局</text><view class="chip-list"><button v-for="item in [{id:'happy',name:'圆满'},{id:'open',name:'开放'},{id:'cliffhanger',name:'悬念'}]" :key="item.id" class="chip" :disabled="busy" @tap="command('set_preferences',{ending:item.id})">{{item.name}}</button></view><text class="field-label">突出一个角色</text><view class="chip-list"><button v-for="role in roles.filter(r=>state?.creation.character_ids.includes(r.id))" :key="role.id" class="chip" :disabled="busy" @tap="command('set_preferences',{focus_role_id:role.id})">{{role.name}}</button></view><view v-if="state.creation.form==='series'"><text class="field-label">重新规划集数（当前 {{state.creation.series_episodes}} 集）</text><view class="chip-list"><button v-for="n in [3,6,12,24]" :key="n" class="chip" :disabled="busy" @tap="command('set_preferences',{series_episodes:n})">{{n}} 集</button></view></view></view>
 <button v-if="can('confirm_outline')" class="warm-button full-button" :disabled="busy" @tap="command('confirm_outline',{target_id:state.plan_id,fingerprint:state.outline_fingerprint})">按这个方向写剧本</button></view>
 <view v-if="can('change')||can('revise_outline')" class="paper-panel section-gap"><text class="field-label">想调整一下？</text><view class="chip-list"><button v-for="item in [{id:'warmer',name:'更温暖'},{id:'lighter',name:'更轻松'},{id:'tension',name:'更紧张'},{id:'new_direction',name:'换一个方向'}]" :key="item.id" class="chip" :disabled="busy" @tap="change(item.id)">{{item.name}}</button></view><view v-if="can('change')&&!can('revise_outline')" class="spaced"><text class="field-label">调整从哪里开始？</text><view class="chip-list"><button class="chip" :class="{selected:!targetScene}" @tap="targetScene=''">后续剧情</button><button v-for="(key,i) in state.scene_keys" :key="key" class="chip" :class="{selected:targetScene===key}" @tap="targetScene=key">第{{i+1}}幕</button></view><view v-if="targetScene" class="chip-list spaced"><button class="chip" :class="{selected:changeScope==='following'}" @tap="changeScope='following'">从这里调整后续</button><button class="chip" :class="{selected:changeScope==='scene'}" @tap="changeScope='scene'">只改这一幕</button></view></view><input v-model="text" maxlength="2000" class="form-input spaced" placeholder="也可以补充一句要求（选填）"/><button class="outline-button full-button" :disabled="busy||!text.trim()" @tap="change()">提交调整</button></view>
 <view v-if="can('confirm_change')" class="paper-panel section-gap"><text class="copy">从第{{(state.pending_change?.start||0)+1}}幕开始调整，{{state.pending_change?.scope==='scene'?'只改这一幕':'同时调整后续'}}；之前的内容保留。</text><button class="warm-button full-button" :disabled="busy" @tap="confirmChange">确认调整范围</button></view>
 <view v-for="(key,i) in state.scene_keys" :key="key" class="paper-panel section-gap"><text class="section-title serif">第{{i+1}}幕 · {{state.outline?.scenes[i]?.title}}</text>
 <text v-for="line in state.scenes[i]?.scene.utterances||[]" :key="line.line_id" class="copy">{{speaker(line.speaker_role_id)}}：{{line.text}}</text><text v-if="previews[key]" class="copy">{{previews[key].text}}</text>
 <template v-if="can('change')"><view class="chip-list spaced"><button class="chip" :disabled="busy" @tap="change('interaction',key)">增加互动</button><button class="chip" :disabled="busy" @tap="change('faster',key,'scene')">只让本幕更紧凑</button><button class="chip" :disabled="busy" @tap="change('suspense',key)">保留悬念</button><button v-for="choice in state.outline?.scenes[i]?.choices||[]" :key="choice.id" class="chip" :disabled="busy" @tap="change(choice.id,key)">{{choice.title}}</button></view></template>
 <template v-if="state.backgrounds[key]"><text class="small-note spaced">背景：{{({disabled:'未启用生图',queued:'等待生成',running:'正在生成',ready:'已完成',failed:'生成失败，可重试',stale:'已过期'} as any)[state.backgrounds[key].status]}}</text><image v-if="images[key]&&state.backgrounds[key].status==='ready'" :src="images[key]" mode="widthFix" class="background"/><text class="copy small-note">{{state.backgrounds[key].spec.environment}}</text><button class="text-link spaced" @tap="showBackground[key]=!showBackground[key]">{{showBackground[key]?'收起背景提示词':'查看背景提示词'}}</button><text v-if="showBackground[key]" class="copy small-note">{{state.backgrounds[key].spec.prompt}}</text><button v-if="images[key]&&state.backgrounds[key].status==='ready'" class="outline-button full-button" @tap="download(key)">下载 16:9 背景图</button><button v-if="state.backgrounds[key].status==='failed'" class="outline-button full-button" :disabled="busy" @tap="command('retry_background',{target_id:key})">重试背景图</button></template></view>
 <view v-if="can('confirm_script')" class="paper-panel section-gap"><text class="copy">确认将冻结当前剧本版本。你仍可创建修改版本，之前的版本会保留。背景图片供预览与下载。</text><button class="warm-button full-button" :disabled="busy" @tap="command('confirm_script',{target_id:state.delivery?.story_version_id,fingerprint:state.script_fingerprint})">确认当前剧本</button></view>
 <view class="paper-panel section-gap"><button v-if="state.delivery" class="warm-button full-button" @tap="exportStory">导出剧本与背景规格</button><text v-if="state.version_history?.length" class="small-note spaced">已保留 {{state.version_history.length}} 个历史确认版本，导出文件包含这些版本，可供核对和后续接入。</text><button v-if="can('next_episode')&&state.creation.form==='series'&&state.episode_number<state.creation.series_episodes" class="outline-button full-button" :disabled="busy" @tap="command('next_episode')">继续下一集</button><button class="outline-button full-button" @tap="fresh">再创作一个故事</button></view>
</template></view></FeatureLayout></template>
<style scoped>.copy{display:block;white-space:pre-wrap;line-height:1.85;margin:18rpx 0}.direction{display:block;text-align:left;width:100%;padding:24rpx 0;border-bottom:1px solid #eadcc9}.background{display:block;width:100%;margin-top:20rpx;border-radius:12rpx}</style>
