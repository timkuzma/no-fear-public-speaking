"""Private loopback browser acceptance with synthetic fixtures only."""
import json
import tempfile
import time
import uuid
import wave
from pathlib import Path
from browser_flow_server import create_fixture
from server.analytics_events import grant_owner
from server.app import ph


def seed(app):
    store=app.state.store
    owner=uuid.uuid4().hex;participant=uuid.uuid4().hex;moment=time.time()
    with store.connect() as db:
        for uid,email,name in [(owner,'analytics-owner@example.test','Владелец тестового стенда'),(participant,'participant@example.test','Тестовый участник')]:
            db.execute('INSERT INTO users VALUES(?,?,?,?,?,?,?,?)',(uid,email,name,ph.hash('SyntheticAnalytics2026'),'student',1,0,moment-15*86400))
        for n in range(4):
            pid=uuid.uuid4().hex;at=moment-(14-n*3)*86400;config={'scenario':'speech','topic':'Синтетический проект','duration':3,'questions':n%2==0,'criteria':''}
            db.execute("INSERT INTO practices(id,user_id,config,created,status,questions) VALUES(?,?,?,?,?,?)",(pid,participant,json.dumps(config,ensure_ascii=False),at,'draft',json.dumps(['Кому поможет идея?','Как применить решение?','Что попробуешь дальше?'])))
            sid=uuid.uuid4().hex
            with wave.open(str(store.media/(sid+'.wav')),'wb') as wav:
                wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(16000);wav.writeframes(b'\x00\x01'*32000)
            db.execute('INSERT INTO segments VALUES(?,?,?,?,?,?,?,?)',(sid,pid,'speech',0,sid+'.wav',2,'Это синтетическая речь для проверки интерфейса.',at+10))
            if config['questions']:
                for i in (1,2,3):db.execute('INSERT INTO segments VALUES(?,?,?,?,?,?,?,?)',(uuid.uuid4().hex,pid,'answer',i,sid+'.wav',2,'Это синтетический ответ.',at+20+i))
            report={'schema_version':2,'strengths':[{'title':'Назван адресат','observation':'Тестовое наблюдение.','evidence':'синтетическая речь'}],'recommendations':[{'title':'Уточни пример','observation':'Тестовый разбор.','action':'Добавь пример в следующей попытке.','evidence':'синтетическая речь'}],'criteria':[],'provenance':{'report_prompt_version':'synthetic-only'}}
            jid=uuid.uuid4().hex;db.execute("INSERT INTO jobs(id,practice_id,kind,status,stage,created) VALUES(?,?,?,?,?,?)",(jid,pid,'report','pending','queued',at+30))
            db.execute("UPDATE jobs SET status='succeeded',finished=?,result=? WHERE id=?",(at+35,json.dumps(report,ensure_ascii=False),jid))
            db.execute("UPDATE practices SET status='ready',report=? WHERE id=?",(json.dumps(report,ensure_ascii=False),pid))
            usage={'model':'synthetic-text-model','operation':'report','attempts':[
                {'input_tokens':100*(n+1),'output_tokens':None if n==0 else 10*(n+1)}]}
            db.execute('INSERT INTO usage VALUES(?,?,?,?,?)',(uuid.uuid4().hex,jid,participant,at+35,json.dumps(usage)))
    grant_owner(store,'analytics-owner@example.test')
    from server.analytics_view import configure
    configure(store,'SyntheticViewerPassword2026!')


if __name__=='__main__':
    import argparse,uvicorn
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8095);args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='nfs-analytics-qa-') as directory:
        app=create_fixture(directory,f'http://127.0.0.1:{args.port}',test_banner=True);seed(app)
        uvicorn.run(app,host='127.0.0.1',port=args.port,access_log=False)
