import { computed, ref, watch } from 'vue';

export const VirtualRoutes = {
 props:['request','userId','state'],
 setup(props:any){
  const routes=ref<any[]>([]),library=ref<any[]>([]),selected=ref<number|null>(null),libraryRoute=ref<any>(null),error=ref(''),busy=ref(false),draft=ref<any>(null);
  const route=computed(()=>libraryRoute.value||routes.value.find(r=>r.id===selected.value));
  const origin=ref(0);
  let generation=0,userVersion=0;
  async function load(){const ticket=++generation;try{const [values,bundled]=await Promise.all([props.request('routes'),props.request('routes/library')]);if(ticket===generation){routes.value=values;library.value=bundled;}}catch(e:any){if(ticket===generation)error.value=e.message;}}
  watch(()=>props.userId,()=>{userVersion++;generation++;busy.value=false;error.value='';routes.value=[];selected.value=null;libraryRoute.value=null;draft.value=null;if(props.userId)load();},{immediate:true});
  function choose(id:number){libraryRoute.value=null;selected.value=id;origin.value=props.state.distance||0;}
  async function chooseLibrary(id:string){busy.value=true;error.value='';const version=userVersion;try{const value=await props.request('routes/library/'+encodeURIComponent(id));if(version===userVersion){selected.value=null;libraryRoute.value=value;origin.value=props.state.distance||0;}}catch(e:any){if(version===userVersion)error.value=e.message;}finally{if(version===userVersion)busy.value=false;}}
  async function importLibrary(){if(!libraryRoute.value)return;busy.value=true;error.value='';const version=userVersion,user=props.userId;try{const value=await props.request('routes/library/'+encodeURIComponent(libraryRoute.value.library_id)+'/import',{expected_user_id:user});if(version!==userVersion)return;await load();if(version===userVersion)choose(value.id);}catch(e:any){if(version===userVersion)error.value=e.message;}finally{if(version===userVersion)busy.value=false;}}
  const progress=computed(()=>route.value?Math.max(0,Math.min(route.value.distance_metres,((props.state.distance||0)-origin.value)*1000)):0);
  const path=computed(()=>{
   const points=route.value?.points||[];if(!points.length)return '';
   const minX=Math.min(...points.map((p:any)=>p.longitude)),maxX=Math.max(...points.map((p:any)=>p.longitude));
   const minY=Math.min(...points.map((p:any)=>p.latitude)),maxY=Math.max(...points.map((p:any)=>p.latitude));
   return points.map((p:any)=>`${20+(p.longitude-minX)/(maxX-minX||1)*760},${230-(p.latitude-minY)/(maxY-minY||1)*210}`).join(' ');
  });
  const elevation=computed(()=>{
   const r=route.value;if(!r?.elevation_available)return '';
   const heights=r.points.map((p:any)=>p.elevation_m),low=Math.min(...heights),high=Math.max(...heights);
   return r.points.map((p:any,i:number)=>`${20+r.cumulative_metres[i]/r.distance_metres*760},${140-(p.elevation_m-low)/(high-low||1)*110}`).join(' ');
  });
  async function readFile(event:any){
   error.value='';draft.value=null;
   const version=userVersion;
   try{
    const file=event.target.files?.[0];if(!file)return;if(file.size>2_000_000)throw Error('Datei höchstens 2 MB.');
    const text=await file.text();if(version!==userVersion)return;let points:any[];
    if(file.name.toLowerCase().endsWith('.gpx')){
     if(/<!DOCTYPE|<!ENTITY/i.test(text))throw Error('GPX mit externen Entitäten wird nicht unterstützt.');
     const xml=new DOMParser().parseFromString(text,'application/xml');
     if(xml.querySelector('parsererror')||xml.querySelectorAll('trkseg').length>1)throw Error('Bitte eine zusammenhängende GPX-Strecke importieren.');
     const nodes=[...xml.querySelectorAll('trkpt,rtept')];
     points=nodes.map((p:any)=>{if(!p.hasAttribute('lon')||!p.hasAttribute('lat'))throw Error('Koordinate fehlt.');if(!p.getAttribute('lon').trim()||!p.getAttribute('lat').trim())throw Error('Leere Koordinate.');const alt=p.querySelector('ele');return {longitude:Number(p.getAttribute('lon')),latitude:Number(p.getAttribute('lat')),elevation_m:alt?.textContent?.trim()?Number(alt.textContent):null};});
    }else{
     const value=JSON.parse(text),geometry=value.type==='Feature'?value.geometry:value;
     if(geometry.type!=='LineString'||!Array.isArray(geometry.coordinates))throw Error('GeoJSON muss genau eine LineString-Geometrie enthalten.');
     points=geometry.coordinates.map((p:any)=>({longitude:p[0],latitude:p[1],elevation_m:p.length>2?p[2]:null}));
    }
    if(points.length<2||points.length>3000||points.some(p=>!Number.isFinite(p.longitude)||!Number.isFinite(p.latitude)||(p.elevation_m!=null&&!Number.isFinite(p.elevation_m))))throw Error('2–3000 gültige Koordinaten benötigt. Fehlende Höhen bleiben unbekannt.');
    draft.value={name:file.name.replace(/\.(gpx|geojson|json)$/i,'').slice(0,80),points,source:'file',attribution:''};
   }catch(e:any){if(version===userVersion)error.value=e.message;}
  }
  async function save(){busy.value=true;error.value='';const version=userVersion,user=props.userId;try{const value=await props.request('routes',{...draft.value,expected_user_id:user});if(version!==userVersion)return;await load();if(version===userVersion){choose(value.id);draft.value=null;}}catch(e:any){if(version===userVersion)error.value=e.message;}finally{if(version===userVersion)busy.value=false;}}
  async function remove(r:any){if(!window.confirm('Diese importierte Strecke löschen?'))return;busy.value=true;const version=userVersion,user=props.userId;try{await props.request('routes/'+r.id+'/delete',{expected_user_id:user,confirm:true});if(version!==userVersion)return;selected.value=null;await load();}catch(e:any){if(version===userVersion)error.value=e.message;}finally{if(version===userVersion)busy.value=false;}}
  return {routes,library,libraryRoute,selected,error,busy,draft,route,path,elevation,progress,readFile,save,choose,chooseLibrary,importLibrary,remove};
 },
 template:`<section class="virtual-routes card feature-form"><h2>Reale Streckendaten · P2-Vorschau</h2><p>Eine geladene Rundstrecke mit echten Koordinaten und amtlichen Höhen auswählen oder eigene GPX-/GeoJSON-Dateien importieren. Die 2D-Vorschau steuert keinen Widerstand. Eine 3D-Fahrt ist noch offen.</p><h3>Geladene Rundstrecken · offline verfügbar</h3><div class="route-list route-library"><article v-for="r in library" :key="r.id"><button class="button secondary" :disabled="busy" @click="chooseLibrary(r.id)">{{r.name}}<span v-if="r.distance_metres"> · {{(r.distance_metres/1000).toFixed(1)}} km</span></button></article></div><p v-if="!library.length">Keine mitgelieferten Streckendaten verfügbar.</p><h3>Eigene Strecken</h3><label class="route-file">GPX / GeoJSON importieren<input type="file" accept=".gpx,.geojson,.json" @change="readFile"></label><p v-if="error" class="alert" role="alert">{{error}}</p><div v-if="draft" class="feature-fields"><label>Streckenname<input v-model="draft.name" maxlength="80"></label><label>Quelle<select v-model="draft.source"><option value="file">Eigene Datei</option><option value="openstreetmap">Aus OpenStreetMap abgeleitet</option></select></label><label>Quellenangabe<input v-model="draft.attribution" placeholder="z. B. © OpenStreetMap contributors"></label><button class="button primary" :disabled="busy" @click="save">Strecke speichern</button></div><p v-if="!routes.length">Noch keine Strecke importiert. Es werden keine erfundenen Orts- oder Höhenprofile gezeigt.</p><div class="route-list"><article v-for="r in routes" :key="r.id"><button class="button secondary" @click="choose(r.id)">{{r.name}} · {{(r.distance_metres/1000).toFixed(2)}} km</button><button class="text-button" :disabled="busy" @click="remove(r)">Löschen</button></article></div><template v-if="route"><h3>{{route.name}}</h3><button v-if="libraryRoute" class="button primary" :disabled="busy" @click="importLibrary">Als eigene Strecke übernehmen</button><p>{{route.closed_loop?'Geschlossene Koordinatenlinie':'Offene Strecke'}} · {{route.distance_source}}</p><svg viewBox="0 0 800 250" class="route-map" role="img" aria-label="Vorschau der importierten Streckenkoordinaten"><polyline :points="path" fill="none" stroke="#2f634a" stroke-width="4"/></svg><template v-if="route.elevation_available"><h3>{{route.library_id?'Amtliches Höhenprofil · Bayern':'Importiertes Höhenprofil'}}</h3><svg viewBox="0 0 800 160" class="route-elevation" role="img" aria-label="Höhenprofil aus importierten Höhendaten"><polyline :points="elevation" fill="none" stroke="#b36640" stroke-width="3"/></svg></template><p v-else>Höhenprofil nicht verfügbar: Die Datei enthält keine vollständigen Höhendaten.</p><p>{{route.attribution}} · Quelle {{route.source}}</p><p v-if="route.provenance?.elevation" class="route-provenance">{{route.provenance.elevation.attribution||route.provenance.elevation.source}}<a v-if="route.provenance.elevation.license_url" :href="route.provenance.elevation.license_url" target="_blank" rel="noopener"> · Höhenlizenz</a></p><p v-if="route.library_id"><a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap · ODbL / Quellen und Lizenz</a></p><p>Auf dieser Vorschau zurückgelegt: {{(progress/1000).toFixed(2)}} km aus {{state.mode==='demo'?'simulierten':state.speed_measurement_note?'Gerätemeldungen mit ungeprüfter Distanzeinheit':'erfassten Radfahrwerten'}}. Die Geometrie verändert keine Wattvorgabe.</p></template></section>`
};
