import {describe,it,expect} from 'vitest'
import {sseParser} from '../src/services/story-sessions'
import type {StoryEvent} from '../src/types/story-session'

describe('story session stream',()=>{
 it('parses split UTF-8 text, comments and multiple records',()=>{
  const events:StoryEvent[]=[];const parse=sseParser(e=>events.push(e))
  const raw=': heartbeat\r\n\r\nid: 1\r\ndata: {"seq":1,"payload":{"text":"竹林"}}\r\n\r\nid: 2\ndata: {"seq":2}\n\n'
  for(const char of raw)parse(char)
  expect(events.map(e=>e.seq)).toEqual([1,2]);expect(events[0].payload.text).toBe('竹林')
 })
 it('waits for an entire event rather than rendering partial JSON',()=>{
  const events:StoryEvent[]=[];const parse=sseParser(e=>events.push(e))
  parse('data: {"seq":1');expect(events).toHaveLength(0)
  parse('}\n\n');expect(events).toHaveLength(1)
 })
})
