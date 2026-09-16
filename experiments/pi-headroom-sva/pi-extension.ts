import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { compress } from "headroom-ai";
import { spawnSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { randomUUID } from "node:crypto";

type Json = Record<string, any>;
const here=resolve(import.meta.dirname);
const runRoot=resolve(process.env.SVA_RUN_ROOT || join(here,"runs"));
const task=process.env.SVA_TASK_ID || "";
const cfg=JSON.parse(readFileSync(join(runRoot,"checkpoint.json"),"utf8")).config;
const python=join(here,".venv/bin/python");
const pending: Json[]=[];

function backend(input:Json):Json {
  const proc=spawnSync(python,[join(here,"tool_backend.py")],{input:JSON.stringify({run_root:runRoot,task,...input}),encoding:"utf8"});
  let value:Json; try { value=JSON.parse(proc.stdout||"{}"); } catch { throw new Error(proc.stderr||"backend returned invalid JSON"); }
  if(proc.status!==0||value.error) throw new Error(value.error||proc.stderr||"backend failed");
  return value;
}
function result(value:Json){ return {content:[{type:"text" as const,text:JSON.stringify(value,null,2)}],details:value}; }

export default function(pi:ExtensionAPI){
  pi.registerTool({name:"read_task",label:"Read proof task",description:"Read the authoritative target, RTL path, clock/reset, initialization, parameters, premises, and baselines.",parameters:Type.Object({}),
    async execute(){return result(backend({action:"read_task"}));}});
  pi.registerTool({name:"submit_candidate",label:"Submit helper",description:"Register a declarative helper property for verifier checking.",parameters:Type.Object({candidate_id:Type.String(),expression:Type.String(),dependencies:Type.Array(Type.String()),hypothesis:Type.String()}),
    async execute(_id,p){return result(backend({action:"submit_candidate",...p}));}});
  pi.registerTool({name:"invoke_ebmc",label:"Run EBMC",description:"Record a bounded check or unbounded k-induction, IC3, or BDD proof. Choose bound (k for induction) and timeout_seconds; omitted values use configuration defaults. No fixed maximum depth. For other EBMC options, custom harnesses, solvers, or transformations, use bash and file tools with the run recorder. Only completed unbounded proofs discharge obligations.",parameters:Type.Object({obligation:Type.String(),dependencies:Type.Array(Type.String()),mode:Type.Union([Type.Literal("bounded"),Type.Literal("k-induction"),Type.Literal("ic3"),Type.Literal("bdd")]),bound:Type.Optional(Type.Integer({minimum:1})),timeout_seconds:Type.Optional(Type.Number({exclusiveMinimum:0}))}),
    async execute(_id,p){return result(backend({action:"invoke_ebmc",...p}));}});
  pi.registerTool({name:"inspect_evidence",label:"Inspect evidence",description:"Read a recorded EBMC report by run ID or returned artifact ID. Set original=true for exact uncompressed retrieval.",parameters:Type.Object({run_id:Type.Optional(Type.String()),artifact_id:Type.Optional(Type.String()),file:Type.Optional(Type.String()),original:Type.Boolean()}),
    async execute(_id,p){const v=backend({action:"inspect_evidence",...p});return {content:[{type:"text" as const,text:JSON.stringify(v.classification)},{type:"text" as const,text:v.original}],details:{...v,retrieveOriginal:p.original,compressible:true}};}});
  pi.registerTool({name:"retract_candidate",label:"Retract helper",description:"Retract a candidate and invalidate all dependent candidates.",parameters:Type.Object({candidate_id:Type.String()}),
    async execute(_id,p){return result(backend({action:"retract_candidate",...p}));}});
  pi.on("session_start",()=>{
    pi.setActiveTools(pi.getAllTools().map(tool=>tool.name));
    if(cfg.thinking) pi.setThinkingLevel(cfg.thinking);
    mkdirSync(join(runRoot,"tasks",task),{recursive:true});
    writeFileSync(join(runRoot,"tasks",task,"interface.json"),JSON.stringify({tools:pi.getActiveTools(),thinking:pi.getThinkingLevel(),verifier_defaults:{bound:cfg.filter_bound,k:cfg.direct_induction_bound,timeout_seconds:cfg.verifier_seconds}},null,2)+"\n");
  });

  pi.on("tool_result",async(event,ctx)=>{
    if(event.toolName!=="inspect_evidence"||!event.details?.compressible||event.details.retrieveOriginal) return;
    const raw=event.details.original as string;
    if(Buffer.byteLength(raw)<cfg.compression_threshold_bytes) return;
    const started=performance.now();
    const compressed=await compress([{role:"tool",tool_call_id:event.toolCallId,content:raw}],{model:cfg.model,baseUrl:cfg.headroom_url,timeout:cfg.compression_timeout_seconds*1000,fallback:false,retries:0,tokenBudget:Math.max(256,Math.floor(raw.length/8))});
    const stats={artifact_id:event.details.artifact_id,latency_ms:performance.now()-started,tokens_before:compressed.tokensBefore,tokens_after:compressed.tokensAfter,transformations:compressed.transformsApplied};
    mkdirSync(join(runRoot,"compression"),{recursive:true});
    writeFileSync(join(runRoot,"compression",randomUUID()+".json"),JSON.stringify(stats,null,2)+"\n");
    return {content:[event.content[0],{type:"text",text:(compressed.messages?.[0] as any)?.content||""}],details:{...event.details,original:undefined,compression:stats}};
  });

  pi.on("before_provider_request",(event)=>{
    if(event.payload.model!==cfg.model) throw new Error(`wrong model: ${event.payload.model}`);
    event.payload.max_tokens=cfg.max_output_tokens;
    delete event.payload.reasoning; delete event.payload.reasoning_effort;
    if(cfg.thinking) event.payload.reasoning={effort:cfg.thinking};
    mkdirSync(join(runRoot,"requests"),{recursive:true});
    writeFileSync(join(runRoot,"requests",randomUUID()+".json"),JSON.stringify({model:event.payload.model,reasoning:event.payload.reasoning,max_tokens:event.payload.max_tokens})+"\n");
    delete event.payload.temperature; delete event.payload.top_p; delete event.payload.top_k;
    const inputTokens=Buffer.byteLength(JSON.stringify(event.payload.messages||event.payload.input||[]));
    const usd=(inputTokens*Number(cfg.max_prompt_usd_per_million)+cfg.max_output_tokens*Number(cfg.max_completion_usd_per_million))/1_000_000;
    const request_id=randomUUID(); backend({action:"reserve",request_id,usd}); pending.push({request_id,reserved_usd:usd,model:event.payload.model});
    return event.payload;
  });
  pi.on("after_provider_response",event=>{ if(pending.length) pending[pending.length-1].response={status:event.status,headers:event.headers}; });
  pi.on("message_end",async event=>{
    if(event.message.role!=="assistant"||!pending.length) return;
    const p=pending.shift()!; const usage=(event.message as any).usage||{};
    let metadata:any=undefined;
    const headers=p.response?.headers||{}; const generationId=headers["x-generation-id"]||headers["X-Generation-Id"];
    if(generationId&&process.env.OPENROUTER_API_KEY){
      const response=await fetch("https://openrouter.ai/api/v1/generation?id="+encodeURIComponent(generationId),{headers:{Authorization:"Bearer "+process.env.OPENROUTER_API_KEY},signal:AbortSignal.timeout(15000)});
      if(response.ok) metadata=(await response.json() as any).data;
    }
    const exact=Number(metadata?.total_cost??usage.cost?.total);
    backend({action:"reconcile",request_id:p.request_id,usd:Number.isFinite(exact)?exact:p.reserved_usd,usage:{...usage,model:p.model,response:p.response,openrouter_generation:metadata,cost_source:metadata?"openrouter_generation":"conservative_reservation"}});
  });
}
