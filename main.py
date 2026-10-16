from __future__ import annotations
import os, time, uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

try:
    from anthropic import Anthropic
except Exception:
    Anthropic = None

try:
    from supabase import create_client
except Exception:
    create_client = None

BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title='AutonomyOS AI Agent MVP', version='1.0.0')
TASKS = {}
CLIENTS = []

class OnboardingIn(BaseModel):
    company_name: str = Field(min_length=2, max_length=120)
    contact_name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=5, max_length=200)
    goal: str = Field(min_length=5, max_length=1200)

class AgentTaskIn(BaseModel):
    goal: str = Field(min_length=5, max_length=2000)
    autonomy_mode: Literal['full','approval'] = 'full'
    connector: Literal['demo_crm','demo_email','demo_ops'] = 'demo_crm'

def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def claude_ready():
    return bool(os.getenv('ANTHROPIC_API_KEY') and Anthropic)

def supabase_ready():
    return bool(os.getenv('SUPABASE_URL') and os.getenv('SUPABASE_KEY') and create_client)

def build_plan(goal, connector):
    g = goal.lower()
    intent = 'general_ops'
    if any(k in g for k in ['lead','sales','crm','prospect']): intent='sales_followup'
    elif any(k in g for k in ['customer','support','ticket','complaint']): intent='support_resolution'
    elif any(k in g for k in ['report','summary','analyze','analysis']): intent='analysis_workflow'
    return [
        {'step':1,'name':'Understand objective','status':'completed','detail':f'Classified task as {intent}.'},
        {'step':2,'name':'Prepare tool action','status':'completed','detail':f'Prepared structured action for {connector}.'},
        {'step':3,'name':'Execute / finalize','status':'pending','detail':'Ready for autonomous execution or approval gate.'},
    ]

def call_claude(goal):
    if not claude_ready(): return None
    try:
        client = Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
        msg = client.messages.create(
            model=os.getenv('CLAUDE_MODEL','claude-3-5-haiku-latest'),
            max_tokens=350,
            temperature=0,
            system='Return a concise 3-step plan for an autonomous SaaS agent. Do not claim external execution.',
            messages=[{'role':'user','content':goal}],
        )
        text = ''.join(b.text for b in msg.content if getattr(b,'type','')=='text').strip()
        return {'provider':'claude','plan_text':text}
    except Exception as e:
        return {'provider':'claude_error','plan_text':str(e)}

def tool_result(connector, goal):
    actions={'demo_crm':'CRM follow-up task prepared','demo_email':'Email draft prepared','demo_ops':'Operations task prepared'}
    return {
        'connector':connector,
        'action':actions[connector],
        'payload':{'goal_excerpt':goal[:140],'priority':'high' if any(k in goal.lower() for k in ['urgent','critical','vip']) else 'normal'},
        'external_system_called':False,
        'note':'Demo connector only. No real third-party system was called.'
    }

@app.get('/')
def home(): return FileResponse(BASE_DIR/'index.html')
@app.get('/styles.css')
def styles(): return FileResponse(BASE_DIR/'styles.css', media_type='text/css')
@app.get('/app.js')
def js(): return FileResponse(BASE_DIR/'app.js', media_type='application/javascript')

@app.get('/api/health')
def health():
    return {'status':'ok','claude':'connected' if claude_ready() else 'demo-mode','supabase':'connected' if supabase_ready() else 'demo-mode','vercel_ready':True}

@app.post('/api/onboarding')
def onboard(p: OnboardingIn):
    record={'id':str(uuid.uuid4())[:8], **p.model_dump(), 'created_at':now_iso(), 'storage':'memory'}
    if supabase_ready():
        try:
            sb=create_client(os.getenv('SUPABASE_URL'), os.getenv('SUPABASE_KEY'))
            r=sb.table('clients').insert({'company_name':p.company_name,'contact_name':p.contact_name,'email':p.email,'goal':p.goal}).execute()
            record['storage']='supabase'; record['supabase_result']=bool(r.data)
        except Exception as e:
            record['storage']='memory-fallback'; record['storage_error']=str(e)
    CLIENTS.append(record)
    return record

@app.post('/api/agent/run')
def run_agent(p: AgentTaskIn):
    started=time.perf_counter(); tid=str(uuid.uuid4())[:8]
    plan=build_plan(p.goal,p.connector)
    status='awaiting_approval' if p.autonomy_mode=='approval' else 'completed'
    plan[-1]['status']=status if status=='awaiting_approval' else 'completed'
    rec={
        'task_id':tid,'goal':p.goal,'autonomy_mode':p.autonomy_mode,'status':status,
        'plan':plan,'tool_result':tool_result(p.connector,p.goal),'claude_plan':call_claude(p.goal),
        'created_at':now_iso(),'latency_ms':int((time.perf_counter()-started)*1000),
        'audit':[{'event':'task_received','at':now_iso()},{'event':'plan_created','at':now_iso()},{'event':'tool_action_prepared','at':now_iso()},{'event':status,'at':now_iso()}]
    }
    TASKS[tid]=rec
    return rec

@app.post('/api/agent/approve/{task_id}')
def approve(task_id:str):
    if task_id not in TASKS: raise HTTPException(404,'Task not found')
    t=TASKS[task_id]
    if t['status']=='awaiting_approval':
        t['status']='completed'; t['plan'][-1]['status']='completed'; t['audit'].append({'event':'human_approved','at':now_iso()})
        t['tool_result']['note']='Approval recorded. Demo connector does not call a real external system.'
    return t

@app.get('/api/tasks')
def tasks(): return list(reversed(list(TASKS.values())))
