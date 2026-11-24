import { computed, ref, watch } from 'vue';
import './workout-library.css';

type WorkoutStep = {name:string;seconds:number;watts:number};
const copySteps=(steps:any[]):WorkoutStep[]=>steps.map(s=>({name:String(s.name||'Abschnitt'),seconds:Number(s.seconds),watts:Number(s.watts)}));
const clock=(seconds:number)=>{const value=Math.max(0,Math.round(seconds||0));return `${Math.floor(value/60)}:${String(value%60).padStart(2,'0')}`;};
const sourceLabel=(source:string)=>({preset:'Vorlage',manual:'Lokal / manuell',ai:'KI-Dienst'}[source]||source||'Unbekannt');

/** A shared time-proportional step curve. No decoration or fabricated telemetry. */
export const SegmentPreview = {
 props: {steps:{default:()=>[]},label:{default:'Vorschau der geplanten Leistung'},compact:{default:false}},
 setup(props:any){
  const valid=computed(()=>props.steps.length>0&&props.steps.every((s:any)=>Number.isFinite(Number(s.seconds))&&Number(s.seconds)>0&&Number.isFinite(Number(s.watts))&&Number(s.watts)>=0));
  const total=computed(()=>valid.value?props.steps.reduce((n:number,s:any)=>n+Number(s.seconds),0):0);
  const maximum=computed(()=>valid.value?Math.max(25,...props.steps.map((s:any)=>Number(s.watts))):25);
  const curve=computed(()=>{
   if(!valid.value)return {line:'',area:''};
   let seconds=0;
   const first=106-Number(props.steps[0].watts)/maximum.value*88;
   let line=`M20,${first}`;
   for(const step of props.steps){
    const y=106-Number(step.watts)/maximum.value*88;
    line+=` L${20+seconds/total.value*460},${y}`;
    seconds+=Number(step.seconds);line+=` L${20+seconds/total.value*460},${y}`;
   }
   return {line,area:line+' L480,106 L20,106 Z'};
  });
  return {valid,total,maximum,curve,clock};
 },
 template:`<div class="segment-preview" :class="{compact}"><svg v-if="valid" viewBox="0 0 500 134" role="img" :aria-label="label" preserveAspectRatio="none"><path d="M20 18V106H480" fill="none" stroke="#cbd8c0"/><path d="M20 62H480" stroke="#e1e7da" stroke-dasharray="4 5"/><path :d="curve.area" fill="#cedec1" opacity=".65"/><path :d="curve.line" fill="none" stroke="#456a40" stroke-width="3" stroke-linejoin="round"/><text x="20" y="129">0:00</text><text x="480" y="129" text-anchor="end">{{clock(total)}} min</text><text x="20" y="12">{{maximum}} W</text></svg><p v-else role="status">Keine gültigen Zeit-/Leistungssegmente für eine Vorschau.</p></div>`
};

const WorkoutEditor = {
 props:['value','disabled','limits'],emits:['update:value'],
 setup(props:any,{emit}:any){
  function set(field:string,value:any){emit('update:value',{...props.value,[field]:value});}
  function change(index:number,field:string,value:any){const steps=copySteps(props.value.steps);(steps[index] as any)[field]=field==='name'?value:Number(value);set('steps',steps);}
  function add(){set('steps',[...copySteps(props.value.steps),{name:'Abschnitt',seconds:60,watts:Math.min(props.limits?.maximum??props.limits?.max_watts??400,Math.max(props.limits?.minimum??props.limits?.min_watts??25,75))}]);}
  function remove(index:number){set('steps',props.value.steps.filter((_:any,i:number)=>i!==index));}
  function move(index:number,delta:number){const steps=copySteps(props.value.steps),next=index+delta;if(next<0||next>=steps.length)return;[steps[index],steps[next]]=[steps[next],steps[index]];set('steps',steps);}
  return {set,change,add,remove,move};
 },
 template:`<div class="workout-editor"><p v-if="limits">Aktuelle Profil-/Gerätegrenzen: {{limits.minimum??limits.min_watts}}–{{limits.maximum??limits.max_watts}} W. Beim Start werden diese Grenzen automatisch geprüft.</p><div class="library-fields"><label>Name<input :value="value.name" maxlength="80" :disabled="disabled" @input="set('name',$event.target.value)"></label><label>Kategorie<input :value="value.category" maxlength="60" :disabled="disabled" @input="set('category',$event.target.value)"></label><label>Beschreibung<textarea :value="value.description" maxlength="1000" :disabled="disabled" @input="set('description',$event.target.value)"></textarea></label></div><div class="segment-editor-heading"><span>Abschnitt</span><span>Dauer (s)</span><span>Sollwert (W)</span><span>Reihenfolge</span></div><div v-for="(step,index) in value.steps" :key="index" class="segment-editor-row"><input :value="step.name" :aria-label="'Name Abschnitt '+(index+1)" maxlength="60" :disabled="disabled" @input="change(index,'name',$event.target.value)"><input :value="step.seconds" :aria-label="'Sekunden Abschnitt '+(index+1)" type="number" min="1" max="7200" step="1" :disabled="disabled" @input="change(index,'seconds',$event.target.value)"><input :value="step.watts" :aria-label="'Watt Abschnitt '+(index+1)" type="number" :min="limits?.minimum??limits?.min_watts??null" :max="limits?.maximum??limits?.max_watts??null" step="1" :disabled="disabled" @input="change(index,'watts',$event.target.value)"><div class="segment-order"><button class="button secondary" :aria-label="'Abschnitt '+(index+1)+' nach oben'" :disabled="disabled||index===0" @click="move(index,-1)">↑</button><button class="button secondary" :aria-label="'Abschnitt '+(index+1)+' nach unten'" :disabled="disabled||index===value.steps.length-1" @click="move(index,1)">↓</button><button class="text-button" :aria-label="'Abschnitt '+(index+1)+' entfernen'" :disabled="disabled||value.steps.length===1" @click="remove(index)">Entfernen</button></div></div><button class="button secondary" :disabled="disabled||value.steps.length>=100" @click="add">Abschnitt hinzufügen</button></div>`
};

export const WorkoutCatalog = {
 components:{SegmentPreview,WorkoutEditor},props:['request','userId','disabled','plans'],emits:['changed','prepare'],
 setup(props:any,{emit}:any){
  const items=ref<any[]>([]),limits=ref<any>(null),busy=ref(false),error=ref(''),notice=ref('');
  const search=ref(''),category=ref('Alle'),minutes=ref(0),favorites=ref(false),details=ref<any>(null);
  const editor=ref<any>(null),editingId=ref<number|null>(null),editingRevision=ref<number|null>(null);
  let loadTicket=0;
  const categories=computed(()=>['Alle',...new Set(items.value.map(p=>p.category||p.meta?.category||'Eigene'))]);
  const visible=computed(()=>items.value.filter(p=>(!search.value||`${p.name} ${p.description||''} ${p.category||''}`.toLocaleLowerCase('de-DE').includes(search.value.toLocaleLowerCase('de-DE')))&&(category.value==='Alle'||(p.category||p.meta?.category||'Eigene')===category.value)&&(!minutes.value||Math.round(p.duration_seconds/60)===Number(minutes.value))&&(!favorites.value||p.favorite)));
  async function refresh(){const ticket=++loadTicket;try{const data=await props.request('catalog');if(ticket===loadTicket){items.value=data.plans||data;limits.value=data.power_limits;}}catch(e:any){if(ticket===loadTicket)error.value=e.message;}}
  watch(()=>props.userId,()=>{items.value=[];details.value=null;editor.value=null;error.value='';notice.value='';if(props.userId)refresh();},{immediate:true});
  watch(()=>props.plans,()=>{if(props.userId)refresh();});
  const owned=(body:any)=>({...body,expected_user_id:props.userId});
  async function perform(action:()=>Promise<void>){busy.value=true;error.value='';notice.value='';try{await action();}catch(e:any){error.value=e.message;}finally{busy.value=false;}}
  const duration=computed(()=>editor.value?.steps.reduce((n:number,s:any)=>n+Number(s.seconds||0),0)||0);
  function newPlan(){editingId.value=null;editingRevision.value=null;details.value=null;editor.value={name:'Mein Training',category:'Eigene',description:'',steps:[{name:'Einrollen',seconds:300,watts:50},{name:'Ausdauer',seconds:900,watts:100},{name:'Ausrollen',seconds:300,watts:40}]};}
  function edit(plan:any){editingId.value=plan.editable===false?null:plan.id;editingRevision.value=plan.revision;details.value=null;editor.value={name:plan.name+(plan.editable===false?' · eigene Kopie':''),category:plan.category||'Eigene',description:plan.description||'',steps:copySteps(plan.steps)};}
  async function save(){await perform(async()=>{const path=editingId.value?'catalog/'+editingId.value+'/update':'catalog';const result=await props.request(path,owned({...editor.value,duration_seconds:duration.value,...(editingId.value?{expected_revision:editingRevision.value}:{})}));editor.value=null;await refresh();emit('changed');notice.value='Profil gespeichert. Es wurde kein Training gestartet.';if(result.plan)details.value=result.plan;});}
  async function favorite(plan:any){await perform(async()=>{await props.request('catalog/'+plan.id+'/favorite',owned({favorite:!plan.favorite}));await refresh();});}
  async function duplicate(plan:any){await perform(async()=>{await props.request('catalog/'+plan.id+'/duplicate',owned({expected_revision:plan.revision,name:plan.name+' · Kopie'}));await refresh();emit('changed');notice.value='Kopie erstellt. Das ursprüngliche Profil bleibt erhalten.';});}
  async function remove(plan:any){if(!window.confirm('Trainingsprofil „'+plan.name+'“ löschen? Abgeschlossene Einheiten bleiben erhalten.'))return;await perform(async()=>{await props.request('catalog/'+plan.id+'/delete',owned({expected_revision:plan.revision,confirm:true}));details.value=null;await refresh();emit('changed');notice.value='Trainingsprofil gelöscht.';});}
  function prepare(plan:any){
   if(busy.value||props.disabled)return;
   // The catalog already has the profile. Loading it into the cockpit is a
   // local selection; validation and device checks belong to the Start click.
   details.value=null;emit('prepare',plan.id,null,plan);
  }
  return {items,limits,busy,error,notice,search,category,minutes,favorites,details,editor,editingId,categories,visible,duration,refresh,newPlan,edit,save,favorite,duplicate,remove,prepare,clock,sourceLabel};
 },
 template:`<section class="workout-library" aria-label="Trainingskatalog"><div class="library-intro card"><div><p class="eyebrow">DEIN TRAININGSKATALOG</p><h2>Ein Profil für deinen nächsten Schritt.</h2><p>Echte Zeit-/Leistungskurven aus gespeicherten Segmenten. Auswahl und Vorbereitung starten keine Einheit.</p></div><button class="button primary" :disabled="busy||disabled" @click="newPlan">Profil erstellen</button></div><p v-if="error" class="alert" role="alert">{{error}}</p><p v-if="notice" class="library-notice" role="status">{{notice}}</p>
 <div v-if="editor" class="library-overlay" @click.self="!busy&&(editor=null)"><section class="card library-editor" role="dialog" aria-modal="true" aria-label="Trainingsprofil bearbeiten"><div class="library-section-heading"><h2>{{editingId?'Trainingsprofil bearbeiten':'Neues Trainingsprofil'}}</h2><button class="text-button" :disabled="busy" @click="editor=null">Abbrechen</button></div><WorkoutEditor v-model:value="editor" :disabled="busy||disabled" :limits="limits"/><SegmentPreview :steps="editor.steps" label="Vorschau des bearbeiteten Trainingsprofils"/><p>Gesamtdauer {{clock(duration)}} min · Änderungen werden beim Start automatisch geprüft.</p><button class="button primary" :disabled="busy||disabled" @click="save">Trainingsprofil speichern</button></section></div>
 <div class="library-filters"><label>Profil suchen<input v-model="search" type="search" placeholder="Name, Ziel oder Beschreibung"></label><label>Ziel<select v-model="category" aria-label="Trainingsziel filtern"><option v-for="value in categories" :value="value">{{value}}</option></select></label><label>Dauer<select v-model.number="minutes" aria-label="Trainingsdauer filtern"><option :value="0">Alle Dauern</option><option v-for="value in [20,30,35,45,60,90,120]" :value="value">{{value}} min</option></select></label><label class="library-checkbox"><input v-model="favorites" type="checkbox">Nur Favoriten</label></div>
 <p v-if="!visible.length" class="library-empty">Kein Profil passt zu diesen Filtern.</p><div class="plan-grid catalog-grid"><article v-for="plan in visible" :key="plan.id" class="card plan-card catalog-card"><div class="catalog-card-top"><span class="eyebrow">{{plan.category||'Eigene'}} · {{sourceLabel(plan.source)}}</span><button class="favorite-button" :aria-label="(plan.favorite?'Favorit entfernen: ':'Als Favorit markieren: ')+plan.name" :aria-pressed="!!plan.favorite" :disabled="busy||disabled" @click="favorite(plan)">{{plan.favorite?'★':'☆'}}</button></div><button class="profile-preview-button" :aria-label="'Details zu '+plan.name" @click="details=details?.id===plan.id?null:plan"><SegmentPreview :steps="plan.steps" :label="'Geplante Leistung: '+plan.name" :compact="true"/><h2>{{plan.name}}</h2></button><div class="catalog-metadata"><b>{{clock(plan.duration_seconds)}} min</b><span>{{plan.min_watts}}–{{plan.max_watts}} W</span><span>{{plan.intensity||'Intensität nicht eingestuft'}}</span></div><p>{{plan.description||'Individuelles Zeit-/Leistungsprofil.'}}</p><div class="catalog-status">{{{draft:'Entwurf',accepted:'Übernommen',validated:'Geprüft',ready:'Start vorbereitet'}[plan.status]||'Gespeichert'}}</div><button class="button primary" :disabled="busy||disabled||!plan.steps?.length" @click="prepare(plan)">Training vorbereiten</button><div class="catalog-secondary"><button class="text-button" :disabled="busy||disabled" @click="edit(plan)">{{plan.editable===false?'Als Kopie bearbeiten':'Bearbeiten'}}</button><button class="text-button" :disabled="busy||disabled" @click="duplicate(plan)">Duplizieren</button><button v-if="plan.editable!==false" class="text-button" :disabled="busy||disabled" @click="remove(plan)">Löschen</button></div></article></div>
 <div v-if="details" class="library-overlay" @click.self="details=null"><section class="card library-details" role="dialog" aria-modal="true" :aria-label="'Profildetails: '+details.name"><div class="library-section-heading"><h2>{{details.name}}</h2><button class="text-button" @click="details=null">Details schließen</button></div><SegmentPreview :steps="details.steps" :label="'Leistungsprofil '+details.name"/><p>{{details.description}}</p><ol><li v-for="step in details.steps">{{step.name}} · {{clock(step.seconds)}} min · {{step.watts}} W</li></ol><button class="button primary" :disabled="busy||disabled" @click="prepare(details)">Dieses Training vorbereiten</button></section></div>
 </section>`
};

export const TrainingCoach = {
 components:{SegmentPreview,WorkoutEditor},props:['request','userId','disabled','plans'],emits:['changed','prepare'],
 setup(props:any,{emit}:any){
  const config=ref<any>({external_available:false}),context=ref<any>(null),busy=ref(false),error=ref(''),notice=ref('');
  const goal=ref('endurance'),minutes=ref(30),consent=ref(false),result=ref<any>(null),proposal=ref<any>(null),proposalToken=ref('');
  const saved=ref<any>(null),adoptedRecord=ref<any>(null),validation=ref<any>(null),limits=ref<any>(null),editVersion=ref(0);
  let ticket=0;
  async function refresh(){const current=++ticket;try{const [c,x,library]=await Promise.all([props.request('coach/config'),props.request('coach/context'),props.request('catalog')]);if(current===ticket){config.value=c;context.value=x;limits.value=library.power_limits;}}catch(e:any){if(current===ticket)error.value=e.message;}}
  watch(()=>props.userId,()=>{result.value=null;proposal.value=null;saved.value=null;adoptedRecord.value=null;validation.value=null;consent.value=false;error.value='';notice.value='';if(props.userId)refresh();},{immediate:true});
  watch(proposal,()=>{saved.value=null;validation.value=null;notice.value='';editVersion.value++;},{deep:true});
  const total=computed(()=>proposal.value?.steps.reduce((n:number,s:any)=>n+Number(s.seconds||0),0)||0);
  function owned(body:any){return {...body,expected_user_id:props.userId};}
  async function perform(action:()=>Promise<void>){busy.value=true;error.value='';try{await action();}catch(e:any){error.value=e.message;}finally{busy.value=false;}}
  async function suggest(provider:string){await perform(async()=>{
   const owner=props.userId;
   let data:any;
   try{data=await props.request('coach/suggest',owned({provider,goal:goal.value,minutes:minutes.value,external_consent:provider==='openai'&&consent.value}));}
   finally{if(provider==='openai')consent.value=false;}
   if(owner!==props.userId)return;
   result.value=data;proposal.value={...data.proposal,steps:copySteps(data.proposal.steps)};proposalToken.value=data.proposal_token;saved.value=null;adoptedRecord.value=null;validation.value=null;notice.value='Vorschlag erzeugt. Prüfe die Abschnitte und passe sie bei Bedarf an.';
  });}
  async function adopt(){await perform(async()=>{
   const version=editVersion.value;
   let data:any;
   if(adoptedRecord.value){
    const {source,...profile}=proposal.value;
    data=await props.request('catalog/'+adoptedRecord.value.id+'/update',owned({...profile,duration_seconds:total.value,expected_revision:adoptedRecord.value.revision}));
    await props.request('catalog/'+data.plan.id+'/accept',owned({expected_revision:data.plan.revision}));
   }else{
    data=await props.request('coach/adopt',owned({proposal:{...proposal.value,duration_seconds:total.value},proposal_token:proposalToken.value}));
   }
   if(version!==editVersion.value)return;
   saved.value=data.plan||{id:data.plan_id,revision:data.revision};adoptedRecord.value={...saved.value};validation.value=null;emit('changed');notice.value='Als bearbeitbares Profil im Katalog übernommen. Noch kein Gerätebefehl gesendet.';
  });}
  async function validate(){if(!saved.value)return;await perform(async()=>{const owner=props.userId,version=editVersion.value;const checked=await props.request('catalog/'+saved.value.id+'/validate',owned({expected_revision:saved.value.revision}));if(owner!==props.userId||version!==editVersion.value)return;validation.value=checked;notice.value='Profil geprüft. Im Cockpit genügt ein Klick auf „Training starten“.';});}
  function prepare(){
   if(!saved.value||busy.value||props.disabled)return;
   emit('prepare',saved.value.id,null,saved.value);
  }
  return {config,context,busy,error,notice,goal,minutes,consent,result,proposal,saved,validation,limits,total,suggest,adopt,validate,prepare,clock,sourceLabel};
 },
 template:`<section class="training-coach workout-library" aria-label="Trainingscoach"><section class="card library-intro"><div><p class="eyebrow">VORSCHLAGEN · ANPASSEN · PRÜFEN</p><h2>Deine nächste Einheit mit Begründung.</h2><p>Der lokale Coach funktioniert ohne KI-Schlüssel. Er erstellt nachvollziehbare Vorschläge; eine allgemeine Fitnessdiagnose oder VO₂max wird daraus nicht abgeleitet.</p></div></section><p v-if="error" class="alert" role="alert">{{error}}</p><p v-if="notice" class="library-notice" role="status">{{notice}}</p><section class="card coach-options"><div class="library-fields"><label>Trainingsziel<select v-model="goal"><option value="endurance">Ausdauer</option><option value="recovery">Regeneration</option><option value="interval">Intervalle</option></select></label><label>Gewünschte Dauer (min)<input v-model.number="minutes" type="number" min="11" max="120"></label></div><button class="button primary" :disabled="busy||disabled" @click="suggest('local')">Lokalen Vorschlag erzeugen</button><details class="coach-privacy"><summary>Optionalen KI-Dienst verwenden</summary><p>{{config.disclosure||'Ein externer Dienst kann ausgewählte Trainingszusammenfassungen erhalten. Ohne Zustimmung werden keine Trainingsdaten übertragen.'}}</p><p v-if="!config.external_available" class="coach-unavailable" role="status"><b>KI-Dienst noch nicht eingerichtet.</b> Auf dem Cockpit-Server müssen OPENAI_API_KEY und OPENAI_MODEL konfiguriert sein. Bis dahin kannst du den lokalen Vorschlag nutzen. Eine Zustimmung allein sendet keine Daten.</p><p v-else class="coach-available" role="status">KI-Dienst eingerichtet. Bitte die Datenübertragung für jeden Vorschlag bestätigen.</p><p v-if="disabled">Der Coach ist während eines Trainings, bei fehlender Serververbindung oder aktiver Zwift-Steuerung gesperrt.</p><label class="library-checkbox coach-consent"><input v-model="consent" type="checkbox" :disabled="busy||disabled">Ich stimme der beschriebenen Übertragung für diesen Vorschlag zu.</label><button class="button secondary" :disabled="busy||disabled||!config.external_available||!consent" @click="suggest('openai')">Vorschlag beim KI-Dienst anfordern</button><p v-if="!config.external_available">Der KI-Vorschlag wird verfügbar, sobald der Server eingerichtet und neu gestartet wurde.</p></details><div v-if="context" class="coach-context"><h3>Verwendbare Datengrundlage</h3><p v-if="context.message">{{context.message}}</p><p v-if="context.summary">{{context.summary}}</p><p v-for="note in context.limitations">{{note}}</p></div></section>
 <section v-if="proposal" class="card library-editor coach-proposal"><p class="eyebrow">{{result?.provider==='openai'?'KI-DIENST':'LOKALER VORSCHLAG'}} · KEIN AUTOMATISCHER START</p><h2>{{proposal.name}}</h2><p>{{result?.reason}}</p><p v-for="note in result?.limitations">{{note}}</p><WorkoutEditor v-model:value="proposal" :disabled="busy||disabled" :limits="limits"/><SegmentPreview :steps="proposal.steps" label="Leistungskurve des Coach-Vorschlags"/><p>Gesamtdauer {{clock(total)}} min · {{sourceLabel(proposal.source)}}. Jede Änderung hebt eine vorherige Prüfung auf.</p><ol class="coach-stages"><li :class="{done:!!saved}">Im Katalog übernehmen</li><li :class="{done:!!validation}">Grenzen & Segmente prüfen</li><li>Im Cockpit vorbereiten</li><li>Bewusst starten</li></ol><div class="coach-actions"><button class="button primary" :disabled="busy||disabled||!!saved" @click="adopt">Vorschlag übernehmen</button><button class="button secondary" :disabled="busy||disabled||!saved" @click="validate">Übernommenes Profil prüfen</button><button class="button secondary" :disabled="busy||disabled||!saved" @click="prepare">Start im Cockpit vorbereiten</button></div><p v-if="saved&&!validation" class="validation-pending">Übernommen, noch nicht geprüft. Nach einer Änderung erneut übernehmen; die Startprüfung läuft automatisch.</p><p v-if="validation" class="library-notice">Prüfung erfolgreich. Das Gerät wird erst nach deinem Start im Cockpit angesteuert.</p></section>
 </section>`
};
