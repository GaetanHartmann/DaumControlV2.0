"""Install the verified staging build only while the live trainer is idle."""
from pathlib import Path
import json
import shutil
import subprocess
import time
from datetime import datetime
from urllib.request import urlopen
from urllib.request import Request

live=Path.home()/'daum-studio'
stage=Path.home()/'daum-studio-next'
state=json.load(urlopen('http://127.0.0.1:8000/api/state',timeout=5))
if state['running']:
    raise SystemExit('Update angehalten: Training läuft. Es wurde nichts verändert.')
if state.get('zwift_detail') and state['zwift_detail'].get('armed'):
    raise SystemExit('Update angehalten: Zwift-Steuerung ist freigegeben.')
reconnect_daum=state['mode']=='daum'
backup=live/'backups'/('before-training-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
backup.mkdir(parents=True)
subprocess.run(['systemctl','--user','stop','daum-studio'],check=True)
try:
    shutil.copytree(live/'backend',backup/'backend',ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copytree(live/'frontend'/'dist',backup/'dist')
    shutil.copytree(stage/'backend',live/'backend',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copytree(stage/'frontend'/'dist',live/'frontend'/'dist',dirs_exist_ok=True)
    for name in ['README.md','requirements.txt']:
        shutil.copy2(stage/name,live/name)
    subprocess.run(['systemctl','--user','start','daum-studio'],check=True)
    for attempt in range(15):
        try:
            state=json.load(urlopen('http://127.0.0.1:8000/api/state',timeout=2))
            assert 'zwift_detail' in state
            break
        except Exception:
            if attempt==14:
                raise
            time.sleep(1)
except Exception:
    subprocess.run(['systemctl','--user','stop','daum-studio'],check=False)
    if (backup/'backend').exists():
        shutil.copytree(backup/'backend',live/'backend',dirs_exist_ok=True)
    if (backup/'dist').exists():
        shutil.copytree(backup/'dist',live/'frontend'/'dist',dirs_exist_ok=True)
    subprocess.run(['systemctl','--user','start','daum-studio'],check=False)
    raise
subprocess.run(['systemctl','--user','restart','daum-studio-display'],check=False)
if reconnect_daum:
    try:
        state=json.load(urlopen(Request('http://127.0.0.1:8000/api/mode',data=b'{"mode":"daum"}',headers={'Content-Type':'application/json'}),timeout=10))
    except Exception as error:
        print('Daum bitte erneut verbinden:',str(error))
print(json.dumps({'updated':True,'backup':str(backup),'mode':state['mode'],'running':state['running'],'connected':state['connected']}))
