import { computed, ref, watch } from 'vue';

// Independent forms keep the existing ride controls and plan editor intact.
export const CockpitFeatures = {
 props: ['section', 'userId', 'plans', 'disabled', 'request'],
 emits: ['changed', 'select-plan'],
 setup(props:any, {emit}:any) {
  const busy=ref(false), error=ref(''), form=ref(''), preview=ref<any>(null);
  const generator=ref({kind:'endurance',minutes:30,watts:100,warmup_minutes:5,cooldown_minutes:5,name:''});
  const analysis=ref<any>(null), entries=ref<any[]>([]);
  const assignment=ref<any>({plan_id:null,scheduled_for:'',strength_position:'before',strength:[]}),editingId=ref<number|null>(null);
  const manual=ref<any>({name:'Laufbandtraining',minutes:30,distance_km:'',heart_rate_bpm:'',incline_percent:''});
  const proposal=computed(()=>analysis.value?.proposal);
  let generation=0;
  async function refresh(){
   const ticket=++generation;
   try{
    const [a,p]=await Promise.all([props.request('analysis'),props.request('planner')]);
    if(ticket===generation){analysis.value=a;entries.value=Array.isArray(p)?p:p.entries||[];}
   }catch(e:any){if(ticket===generation)error.value=e.message;}
  }
  watch(()=>[props.userId,props.section],()=>{form.value='';preview.value=null;error.value='';analysis.value=null;entries.value=[];editingId.value=null;assignment.value={plan_id:null,scheduled_for:'',strength_position:'before',strength:[]};if(props.userId)refresh();},{immediate:true});
  watch(generator,()=>preview.value=null,{deep:true});
  async function perform(fn:()=>Promise<void>){busy.value=true;error.value='';try{await fn();}catch(e:any){error.value=e.message;}finally{busy.value=false;}}
  function body(value:any){return {...value,expected_user_id:props.userId};}
  async function generate(){await perform(async()=>{
   const params=new URLSearchParams(Object.entries(generator.value).filter(([k])=>k!=='name').map(([k,v])=>[k,String(v)]));
   preview.value=await props.request('generator/preview?'+params);
  });}
  async function saveGenerated(){await perform(async()=>{
   const result=await props.request('generator/save',body({...generator.value,name:generator.value.name||undefined}));
   emit('changed');form.value='';preview.value=null;emit('select-plan',result.plan_id);
  });}
  async function adopt(){await perform(async()=>{await props.request('planner/adopt',body({ride_id:analysis.value?.ride_id}));emit('changed');await refresh();});}
  async function assign(){await perform(async()=>{
   await props.request(editingId.value?'planner/'+editingId.value+'/edit':'planner',body({...assignment.value,plan_id:assignment.value.plan_id?Number(assignment.value.plan_id):null,scheduled_for:assignment.value.scheduled_for||null}));
   form.value='';emit('changed');await refresh();
  });}
  function edit(entry:any){editingId.value=entry.id;assignment.value={plan_id:entry.plan_id,scheduled_for:entry.scheduled_for||'',strength_position:entry.strength_position,strength:entry.strength.map((v:any)=>({...v}))};form.value='assignment';}
  function moveExercise(index:number,delta:number){const target=index+delta;if(target<0||target>=assignment.value.strength.length)return;const [item]=assignment.value.strength.splice(index,1);assignment.value.strength.splice(target,0,item);}
  function newEntry(){editingId.value=null;assignment.value={plan_id:null,scheduled_for:'',strength_position:'before',strength:[]};form.value=form.value==='assignment'?'':'assignment';}
  async function progress(entry:any,status:string,indices:number[]){await perform(async()=>{
   await props.request('planner/'+entry.id+'/progress',body({status,strength_completed:indices}));await refresh();
  });}
  function toggleExercise(entry:any,index:number){const list=entry.strength_completed||[];progress(entry,entry.status,list.includes(index)?list.filter((n:number)=>n!==index):[...list,index]);}
  async function saveManual(){await perform(async()=>{
   const numberOrNull=(v:any)=>v===''||v==null?null:Number(v);
   await props.request('manual/treadmill',body({name:manual.value.name,seconds:Math.round(Number(manual.value.minutes)*60),distance_km:numberOrNull(manual.value.distance_km),heart_rate_bpm:numberOrNull(manual.value.heart_rate_bpm),incline_percent:numberOrNull(manual.value.incline_percent)}));
   form.value='';emit('changed');await refresh();
  });}
  const fmt=(v:any,unit='')=>v==null?'Nicht verfügbar':Number(v).toLocaleString('de-DE',{maximumFractionDigits:1})+(unit?' '+unit:'');
  return {busy,error,form,preview,generator,analysis,entries,assignment,editingId,edit,newEntry,moveExercise,manual,proposal,refresh,generate,saveGenerated,adopt,assign,progress,toggleExercise,saveManual,fmt};
 },
 template:`<section class="cockpit-features">
  <p v-if="error" class="alert" role="alert">{{error}}</p>
  <template v-if="section==='plans'">
   <button class="button secondary" :disabled="disabled||busy" @click="form=form==='generator'?'':'generator'">Trainingsprofil generieren</button>
   <section v-if="form==='generator'" class="card feature-form"><h2>Dein Trainingsprofil</h2><p>Wattwerte selbst wählen und vor dem Speichern prüfen. Es wird keine Belastbarkeit aus einer einzelnen Fahrt abgeleitet.</p>
    <div class="feature-fields"><label>Trainingsart<select v-model="generator.kind"><option value="endurance">Ausdauer</option><option value="interval">Intervalle</option><option value="recovery">Regeneration</option></select></label><label>Dauer (min)<input v-model.number="generator.minutes" type="number" min="10" max="120"></label><label>Belastungsleistung (W)<input v-model.number="generator.watts" type="number" min="25" max="400"></label><label>Aufwärmen (min)<input v-model.number="generator.warmup_minutes" type="number" min="1" max="20"></label><label>Cooldown (min)<input v-model.number="generator.cooldown_minutes" type="number" min="1" max="20"></label><label>Name (optional)<input v-model="generator.name" maxlength="80"></label></div>
    <button class="button secondary" :disabled="busy" @click="generate">Profilvorschau erstellen</button>
    <div v-if="preview" class="generated-preview"><h3>{{preview.name}}</h3><div class="interval-bars" aria-label="Generiertes Leistungsprofil"><i v-for="step in preview.steps" :style="{height:Math.max(8,step.watts/400*80)+'px',flex:step.seconds}" :title="step.name+' · '+step.watts+' W'"></i></div><ol><li v-for="step in preview.steps">{{step.name}} · {{Math.floor(step.seconds/60)}} min {{step.seconds%60}} s · {{step.watts}} W</li></ol><button class="button primary" :disabled="disabled||busy" @click="saveGenerated">Profil speichern & auswählen</button><p>Danach unter „Wattwerte bearbeiten“ als eigene Vorlage anpassbar.</p></div>
   </section>
  </template>
  <template v-if="section==='activities'">
   <section class="card feature-form"><h2>Entwicklung & nächstes Training</h2><button class="text-button" :disabled="busy" @click="refresh">Auswertung aktualisieren</button>
    <template v-if="analysis"><p>{{analysis.message||analysis.note}}</p><div class="feature-stats"><span>Relative Leistung<b>{{fmt(analysis.watts_per_kg,'W/kg')}}</b></span><span>Intensität<b>{{analysis.intensity?.label||'Nicht verfügbar'}}</b></span><span v-if="analysis.comparison">Vorherige Einheit<b>{{analysis.comparison.note||analysis.comparison.message||fmt(analysis.comparison.power_change_percent,'% Leistung')}}</b></span></div><p v-if="analysis.comparison">Leistungsunterschied: {{fmt(analysis.comparison.power_delta_watts,'W')}}.</p><p v-if="analysis.trend">Leistungsverlauf: erstes Drittel {{fmt(analysis.trend.first_third_watts,'W')}}, letztes Drittel {{fmt(analysis.trend.last_third_watts,'W')}}. {{analysis.trend.note}}</p><p v-for="note in analysis.limitations">{{note}}</p>
     <template v-if="proposal"><h3>{{proposal.name}}</h3><p>{{proposal.reason||analysis.recommendation_reason}}</p><ol><li v-for="step in proposal.steps">{{step.name}} · {{Math.round(step.seconds/60)}} min · {{step.watts}} W</li></ol><button class="button primary" :disabled="disabled||busy" @click="adopt">Vorschlag in meinen Plan übernehmen</button></template>
    </template><p v-else>Für die Auswertung werden echte Einheiten mit ausreichenden Messwerten benötigt.</p>
   </section>
   <button class="button secondary" :disabled="disabled||busy" @click="form=form==='manual'?'':'manual'">Laufbandtraining manuell erfassen</button>
   <section v-if="form==='manual'" class="card feature-form"><h2>Laufbandtraining erfassen</h2><p>Quelle: manuelle Eingabe. Felder ohne Messung leer lassen. Das Laufband wird nicht gesteuert.</p><div class="feature-fields"><label>Bezeichnung<input v-model="manual.name" maxlength="80"></label><label>Dauer (min)<input v-model.number="manual.minutes" type="number" min="1" max="720"></label><label>Distanz (km, optional)<input v-model="manual.distance_km" type="number" min="0" step="0.01"></label><label>Durchschnittspuls (bpm, optional)<input v-model="manual.heart_rate_bpm" type="number" min="30" max="250"></label><label>Steigung (%, optional)<input v-model="manual.incline_percent" type="number" min="-20" max="40" step="0.1"></label></div><button class="button primary" :disabled="disabled||busy" @click="saveManual">Laufbandtraining speichern</button></section>
  </template>
  <template v-if="section==='planner'">
   <section class="card feature-form"><h2>Mein Trainingsplan</h2><p>Persönliche Einheiten aus der bestehenden Profilbibliothek. Krafttraining ist optional und findet vor oder nach dem Radtraining statt.</p><button class="button primary" :disabled="disabled||busy" @click="newEntry()">Einheit planen</button></section>
   <section v-if="form==='assignment'" class="card feature-form"><h3>{{editingId?'Einheit bearbeiten':'Einheit & optionales Kraftprogramm'}}</h3><div class="feature-fields"><label>Radprofil<select v-model="assignment.plan_id"><option :value="null">Bitte auswählen</option><option v-for="plan in plans" :value="plan.id">{{plan.name}}</option></select></label><label>Datum (optional)<input v-model="assignment.scheduled_for" type="date"></label><label>Kraftprogramm<select v-model="assignment.strength_position"><option value="before">Vor dem Radtraining</option><option value="after">Nach dem Radtraining</option></select></label></div>
    <div class="strength-editor" v-for="(exercise,index) in assignment.strength"><label>Übung<input v-model="exercise.name" maxlength="80"></label><label>Variante<input v-model="exercise.variant" maxlength="80" placeholder="z. B. Wand / erhöht"></label><label>Sätze<input v-model.number="exercise.sets" type="number" min="1" max="6"></label><label>Wiederholungen<input v-model.number="exercise.repetitions" type="number" min="1" max="50"></label><label>Pause (s)<input v-model.number="exercise.rest_seconds" type="number" min="10" max="600"></label><div class="exercise-order"><button class="text-button" :disabled="index===0" @click="moveExercise(index,-1)" aria-label="Übung nach oben">↑</button><button class="text-button" :disabled="index===assignment.strength.length-1" @click="moveExercise(index,1)" aria-label="Übung nach unten">↓</button><button class="text-button" @click="assignment.strength.splice(index,1)">Entfernen</button></div></div>
    <div class="feature-actions"><button class="button secondary" @click="assignment.strength.push({name:'Liegestütze',variant:'Wand',sets:2,repetitions:8,rest_seconds:60})">Optionale Kraftübung hinzufügen</button><button class="button secondary" @click="assignment.strength.push({name:'Aufwärmen',variant:'Schulterkreisen',sets:1,repetitions:10,rest_seconds:30})">Aufwärmübung hinzufügen</button><button class="button primary" :disabled="disabled||busy||(!assignment.plan_id&&!assignment.strength.length)" @click="assign">Einheit speichern</button></div>
   </section>
   <p v-if="!entries.length">Noch keine persönlichen Einheiten geplant.</p>
   <article v-for="entry in entries" :key="entry.id" class="card feature-form"><h3>{{entry.plan_name||entry.name||plans.find(p=>p.id===entry.plan_id)?.name}}</h3><p>{{entry.scheduled_for||'Ohne festen Termin'}} · {{entry.status==='completed'?'Abgeschlossen':entry.status==='skipped'?'Übersprungen':'Geplant'}}</p><p v-if="entry.strength?.length">Kraftprogramm {{entry.strength_position==='before'?'vor':'nach'}} dem Radtraining</p><ol><li v-for="(exercise,index) in entry.strength"><label class="exercise-check"><input type="checkbox" :checked="(entry.strength_completed||[]).includes(index)" :disabled="disabled||busy" @change="toggleExercise(entry,index)"><span>{{exercise.name}} · {{exercise.variant}} · {{exercise.sets}} × {{exercise.repetitions}} · {{exercise.rest_seconds}} s Pause</span></label></li></ol><div class="feature-actions"><button class="button secondary" :disabled="disabled||busy" @click="edit(entry)">Bearbeiten</button><button v-if="entry.plan_id" class="button secondary" :disabled="disabled||busy" @click="$emit('select-plan',entry.plan_id)">Radprofil auswählen</button><button class="button primary" :disabled="disabled||busy" @click="progress(entry,'completed',entry.strength_completed||[])">Einheit abgeschlossen</button><button v-if="entry.status==='completed'" class="text-button" :disabled="disabled||busy" @click="progress(entry,'planned',entry.strength_completed||[])">Wieder einplanen</button><button class="text-button" :disabled="disabled||busy" @click="progress(entry,entry.status==='skipped'?'planned':'skipped',entry.strength_completed||[])">{{entry.status==='skipped'?'Wieder einplanen':'Überspringen'}}</button></div></article>
  </template>
 </section>`
};
