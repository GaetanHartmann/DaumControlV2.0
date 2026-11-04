import json, urllib.request
from websockets.sync.client import connect
pages=json.load(urllib.request.urlopen('http://127.0.0.1:9222/json/list'))
page=next(p for p in pages if p['type']=='page')
with connect(page['webSocketDebuggerUrl']) as ws:
    ws.send(json.dumps({'id':1,'method':'Runtime.evaluate','params':{'expression':'JSON.stringify({state:document.readyState,text:document.body.innerText.slice(0,2000),html:document.body.innerHTML.slice(0,500),resources:performance.getEntriesByType("resource").map(r=>({name:r.name,duration:r.duration})),viewport:[innerWidth,innerHeight]})','returnByValue':True}}))
    while True:
        result=json.loads(ws.recv())
        if result.get('id')==1:
            print(json.dumps(result))
            break
