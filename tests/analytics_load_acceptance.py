"""Synthetic capacity check, no real provider calls or production data."""
import json
import sys
import tempfile
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from server.store import Store
from server.analytics_metrics import calculate


def main():
    with tempfile.TemporaryDirectory(prefix='nfs-analytics-load-') as directory:
        store=Store(directory);moment=time.time()
        with store.connect() as db:
            db.executemany('INSERT INTO users VALUES(?,?,?,?,?,?,?,?)',((f'{n:032x}',f'fixture-{n}@example.test','Fixture','not-a-login-hash','student',0,0,moment-14*86400) for n in range(1,10001)))
            db.executemany('INSERT INTO practices(id,user_id,config,created) VALUES(?,?,?,?)',((f'{n+10000:032x}',f'{(n%10000)+1:032x}','{"scenario":"speech","duration":3,"questions":false}',moment-10*86400) for n in range(1,100001)))
            db.executemany('INSERT INTO analytics_events(event_id,kind,origin,occurred,received,release,data) VALUES(?,?,?,?,?,?,?)',((f'load-{n}','request','server_confirmed',moment,moment,'synthetic','{}') for n in range(1000000)))
        elapsed=[]
        for _ in range(3):
            before=time.monotonic()
            with store.connect() as db:data=calculate(db,{})
            elapsed.append(time.monotonic()-before)
            assert data['summary']['registrations']==10000 and data['summary']['practices']==100000
        print(json.dumps({'source':'synthetic only','accounts':10000,'practices':100000,'technical_events':1000000,'seconds':elapsed,'counts_exact':True,'provider_calls':0}))


if __name__=='__main__':main()
