from fastapi.testclient import TestClient
from main import app
client=TestClient(app)
def test_health():
    r=client.get('/api/health'); assert r.status_code==200 and r.json()['status']=='ok'
def test_run():
    r=client.post('/api/agent/run',json={'goal':'Review this urgent sales lead and prepare a CRM follow-up task.','autonomy_mode':'full','connector':'demo_crm'}); assert r.status_code==200 and r.json()['status']=='completed'
def test_approval():
    x=client.post('/api/agent/run',json={'goal':'Prepare an operations action that requires approval.','autonomy_mode':'approval','connector':'demo_ops'}).json(); assert x['status']=='awaiting_approval'; r=client.post(f"/api/agent/approve/{x['task_id']}"); assert r.json()['status']=='completed'
def test_onboarding():
    r=client.post('/api/onboarding',json={'company_name':'Demo Co','contact_name':'Alex Doe','email':'alex@example.com','goal':'Automate lead qualification and onboarding.'}); assert r.status_code==200
