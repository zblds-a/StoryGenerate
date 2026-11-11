export interface StoryCreation {
  idempotency_key:string; form:'short'|'series'; method:'assist'|'idea'|'continue'; idea:string
  genre:string; feeling:string; ending:string; art_style:string; series_episodes:number; character_ids:string[]
  output:'script'|'audio'|'h5'; casting:Record<string,unknown>|null; source_session_id?:string
}
export interface StoryEvent {event_id:string;seq:number;session_id:string;revision:number;generation_epoch:number;type:string;payload:Record<string,any>}
export interface StorySession {
  id:string;revision:number;generation_epoch:number;stage:string;last_seq:number;available_actions:string[]
  creation:StoryCreation;episode_number:number;plan_id:string;outline_fingerprint:string;script_fingerprint:string
  directions:{id:string;title:string;premise:string}[]
  outline:null|{title:string;premise:string;relationships:string[];series_arc:string;episode_summaries:string[];scenes:{title:string;goal:string;choices:{id:string;title:string;premise:string}[]}[]}
  scene_keys:string[];scenes:{scene:{scene_id:string;title:string;utterances:{line_id:string;text:string;kind:string}[]}}[]
  pending_change:null|{instructions:string[];start:number;scope:string}
  backgrounds:Record<string,{status:string;spec:{prompt:string;negative_prompt:string};image?:{sha256:string}}>
  delivery:null|{story_version_id:string;episodes:unknown[]};media:null|{flow_id:string};error_code?:string
}
