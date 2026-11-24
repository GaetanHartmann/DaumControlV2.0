import { computed, onMounted, onUnmounted, reactive, ref, watch, type Ref } from 'vue';
import { WorkoutTimeline } from './training-ui';
import './immersive-cockpit.css';

export type CockpitFullscreenMode = 'timeline' | 'metrics';

/** View state only. This hook never invokes the training or device API. */
export function useCockpitFullscreen(tab:Ref<string>, state:Ref<any>) {
 const active=ref(false), mode=ref<CockpitFullscreenMode>('timeline');
 const supportsNative=ref(false), nativeActive=ref(false);
 let generation=0, disposed=false, ownsNative=false;
 const status=computed(()=>`${state.value.running?(state.value.paused?'Pausiert':'Training läuft'):'Bereit'} · ${nativeActive.value?'Browser-Vollbild':'Bildschirmansicht'}`);
 function lockScroll(value:boolean){document.documentElement.classList.toggle('cockpit-fullscreen-open',value);}
 async function exit(){
  generation++;active.value=false;lockScroll(false);
  if(ownsNative&&document.fullscreenElement){ownsNative=false;try{await document.exitFullscreen();}catch{}}
  nativeActive.value=false;
 }
 async function enter(next:CockpitFullscreenMode='timeline'){
  if(disposed||tab.value!=='Cockpit')return;
  mode.value=next==='metrics'?'metrics':'timeline';
  if(active.value)return;
  const version=++generation;
  active.value=true;lockScroll(true);
  // CSS fills the viewport immediately, including Pi kiosk and unsupported Safari.
  if(!supportsNative.value||document.fullscreenElement)return;
  try{
   await document.documentElement.requestFullscreen();
   if(disposed||version!==generation||!active.value){if(document.fullscreenElement===document.documentElement)await document.exitFullscreen();return;}
   ownsNative=true;nativeActive.value=true;
  }catch{/* A rejected browser request keeps the usable viewport fallback. */}
 }
 function toggle(next?:CockpitFullscreenMode){return active.value&&(!next||next===mode.value)?exit():enter(next||mode.value);}
 function onKey(event:KeyboardEvent){if(event.key==='Escape'&&active.value){event.preventDefault();void exit();}}
 function onNativeChange(){
  if(ownsNative&&!document.fullscreenElement){ownsNative=false;nativeActive.value=false;active.value=false;lockScroll(false);}
 }
 watch(tab,value=>{if(value!=='Cockpit'&&active.value)void exit();});
 onMounted(()=>{
  supportsNative.value=Boolean(document.fullscreenEnabled&&document.documentElement.requestFullscreen);
  document.addEventListener('keydown',onKey);
  document.addEventListener('fullscreenchange',onNativeChange);
 });
 onUnmounted(()=>{
  disposed=true;void exit();document.removeEventListener('keydown',onKey);document.removeEventListener('fullscreenchange',onNativeChange);
 });
 return reactive({active,mode,supportsNative,status,enter,exit,toggle});
}

export const FullscreenTrainingView = {
 components:{WorkoutTimeline},
 props:{
  mode:{default:'timeline'},state:{default:()=>({})},steps:{default:()=>[]},samples:{default:()=>[]},ftp:{default:150},
  elapsed:{default:0},requestedTarget:{default:null},powerLimits:{default:()=>({minimum:25,maximum:400,step:5})},
  busy:{default:false},manualLocked:{default:false},pendingAction:{default:null},online:{default:true},message:{default:''},
 },
 emits:['exit','mode','power','return-plan','action'],
 setup(props:any,{emit}:any){
  const controlsOpen=ref(false), dialog=ref<HTMLElement|null>(null);
  const previousFocus=typeof document==='undefined'?null:document.activeElement as HTMLElement|null;
  function trapFocus(event:KeyboardEvent){
   if(event.key!=='Tab'||!dialog.value)return;
   const nodes=Array.from(dialog.value.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), [tabindex="0"]')).filter(node=>node.getClientRects().length);
   const first=nodes[0],last=nodes.at(-1);
   if(!first){event.preventDefault();return;}
   if(event.shiftKey&&(document.activeElement===first||!dialog.value.contains(document.activeElement))){event.preventDefault();last?.focus();}
   else if(!event.shiftKey&&(document.activeElement===last||!dialog.value.contains(document.activeElement))){event.preventDefault();first.focus();}
  }
  onMounted(()=>{dialog.value?.querySelector<HTMLElement>('.fullscreen-close')?.focus();document.addEventListener('keydown',trapFocus);});
  onUnmounted(()=>{document.removeEventListener('keydown',trapFocus);if(previousFocus?.isConnected)previousFocus.focus();});
  const format=(value:any,digits=0)=>value==null||!Number.isFinite(Number(value))?'—':Number(value).toLocaleString('de-DE',{maximumFractionDigits:digits});
  const clock=(seconds:any)=>seconds==null||!Number.isFinite(Number(seconds))?'—':`${Math.floor(seconds/3600)?Math.floor(seconds/3600)+':':''}${String(Math.floor(seconds/60)%60).padStart(2,'0')}:${String(Math.floor(seconds)%60).padStart(2,'0')}`;
  const measurement=(key:string)=>{
   const item=props.state.measurements?.[key];
   return props.online&&(key==='heart_rate'||props.state.running&&!props.state.paused)&&item?.available&&!item?.stale?item.value:null;
  };
  const source=(key:string)=>{
   const item=props.state.measurements?.[key];
   if(key==='speed'&&props.state.speed_measurement_note)return 'Einheit ungeprüft';
   if(!props.online)return 'Server getrennt';
   if(item?.stale)return 'Signal veraltet';
   if(!item?.available)return 'Nicht verfügbar';
   return {demo:'Simuliert',daum:'Daum-Gerät',ble:'Pulsgurt',calculated:'Berechnet',integrated_power:'Berechnet',daum_x70_field_6:'Gerätemeldung · unverifiziert'}[item?.source as string]||'Nicht verfügbar';
  };
  const target=computed(()=>props.requestedTarget??props.state.requested_target_watts??null);
  const confirmation=computed(()=>{
   const state=props.state,status=state.target_command_status;
   if(state.mode==='demo'||status==='simulated')return 'Simulation · keine Gerätebestätigung';
   if(status==='adjusted')return 'Geräterückmeldung weicht ab';
   if(status==='applied')return 'Vom Gerät zurückgemeldet';
   if(status==='error')return 'Gerätebefehl fehlgeschlagen';
   if(status==='unsupported')return 'Steuerung nicht unterstützt';
   if(status==='paused')return 'Vorgabe für Fortsetzen';
   return status==='unconfirmed'?'Nicht bestätigt':'Rückmeldung ausstehend';
  });
  const confirmed=computed(()=>['applied','adjusted'].includes(props.state.target_command_status)?props.state.applied_target_watts:null);
  const controlLabel=computed(()=>props.state.control_mode==='manual_override'?'Manuell angepasst':props.state.control_mode==='hr'?'Pulsregelung':'Trainingsplan');
  const tiles=computed(()=>{
   const state=props.state,energy=state.measurements?.energy;
   return [
    {key:'actual',label:'Ist-Leistung',value:format(measurement('power')),unit:'W',note:state.power_measurement_note?'Ist nicht nachgewiesen':source('power')},
    {key:'requested',label:'Sollwert angefordert',value:format(target.value),unit:'W',note:controlLabel.value},
    {key:'applied',label:'Geräterückmeldung',value:format(confirmed.value),unit:'W',note:confirmation.value},
    {key:'pulse',label:'Herzfrequenz',value:format(measurement('heart_rate')),unit:'bpm',note:source('heart_rate')},
    {key:'cadence',label:'Trittfrequenz',value:format(measurement('cadence')),unit:'U/min',note:source('cadence')},
    {key:'speed',label:'Geschwindigkeit',value:format(measurement('speed'),1),unit:state.speed_measurement_note?'km/h*':'km/h',note:source('speed')},
    {key:'distance',label:'Distanz',value:format(state.elapsed>0?state.distance:null,2),unit:state.speed_measurement_note?'km*':'km',note:state.speed_measurement_note?'Einheit ungeprüft':props.online?'Aufgezeichnete Distanz':'Zuletzt aufgezeichnet'},
    {key:'elapsed',label:'Trainingszeit',value:clock(state.elapsed),unit:'',note:state.paused?'Pausiert':state.running?'Läuft':'Bereit'},
    {key:'remaining',label:'Restzeit',value:clock(state.duration?Math.max(0,state.duration-state.elapsed):null),unit:'',note:state.duration?'Bis Planende':'Nicht festgelegt'},
    {key:'energy',label:'Mechanische Arbeit',value:format(energy?.available&&!energy?.stale?energy.value:null),unit:'kJ',note:energy?.available?(state.mode==='demo'?'Aus simulierter Leistung':props.online?'Aus verifizierter Leistung':'Zuletzt aufgezeichnet'):'Nicht verfügbar'},
    {key:'calories',label:'Kalorien',value:format(measurement('calories')),unit:'kcal',note:source('calories')},
    {key:'phase',label:'Aktive Profilphase',value:state.step_name||'—',unit:'',note:state.running&&state.steps?.length?`Abschnitt ${(state.step_index||0)+1} / ${state.steps.length}`:'Kein Stufenplan aktiv',text:true},
    {key:'next',label:'Plan jetzt / nächste Stufe',value:`${format(state.planned_target_watts)} / ${format(state.next_step?.watts)}`,unit:'W',note:state.next_step?.name||'Keine nächste Stufe'},
    {key:'ergometer',label:'Ergometer',value:state.mode==='demo'?'Simulation':state.connected?'Verbunden':'Getrennt',unit:'',note:props.online?'Daum-Verbindung':'Server getrennt',text:true},
    {key:'sensor',label:'Pulsgurt',value:state.hr_connected?(state.hr_fresh?'Verbunden':'Kein frisches Signal'):'Nicht verbunden',unit:'',note:state.hr_connected?'Separater Pulssensor':'Optional im Wattmodus',text:true},
    {key:'reported',label:'Gerätemeldung',value:format(measurement('reported_power')),unit:'W',note:state.power_measurement_note?'Keine unabhängige Ist-Leistung':'Separater Rohwert'},
    {key:'control',label:'Steuerungsmodus',value:controlLabel.value,unit:'',note:state.plan_name||'Freies Training',text:true},
   ];
  });
  function power(value:number,sourceName:string){
   if(props.manualLocked||!Number.isFinite(value))return;
   const {minimum,maximum}=props.powerLimits;
   emit('power',Math.max(minimum,Math.min(maximum,value)),sourceName);
  }
  return {dialog,controlsOpen,format,measurement,target,tiles,confirmed,confirmation,controlLabel,power};
 },
 template:`<section ref="dialog" class="fullscreen-training-view" role="dialog" aria-modal="true" :aria-label="mode==='timeline'?'Zeitachse im Vollbild':'Kennzahlen im Vollbild'" :data-fullscreen-view="mode">
  <div class="fullscreen-training-header">
   <div class="fullscreen-view-choice" role="group" aria-label="Vollbildansicht wählen"><button :aria-pressed="mode==='timeline'" :class="{chosen:mode==='timeline'}" @click="$emit('mode','timeline')">Zeitachse</button><button :aria-pressed="mode==='metrics'" :class="{chosen:mode==='metrics'}" @click="$emit('mode','metrics')">Kennzahlen</button></div>
   <span class="fullscreen-session-label" role="status">{{!online?'Server getrennt':state.running?(state.paused?'Pausiert':'Training läuft'):'Bereit'}} · {{state.mode==='demo'?'Demo':state.connected?'Daum verbunden':'Daum getrennt'}}</span>
   <div class="fullscreen-session-actions"><button v-if="state.running" class="fullscreen-pause" :disabled="busy||!online||state.zwift_detail?.armed" @click="$emit('action','pause')">{{pendingAction==='pause'?'Bitte warten …':state.paused?'Fortsetzen':'Pause'}}</button><button v-if="state.running" class="fullscreen-stop" :disabled="busy||!online" @click="$emit('action','stop')">{{pendingAction==='stop'?'Speichert …':'Stopp'}}</button><button class="fullscreen-close" aria-label="Vollbild schließen" @click="$emit('exit')"><span aria-hidden="true">×</span><span>Schließen</span></button></div>
  </div>
  <div v-if="message||state.error||!online" class="fullscreen-error" role="alert">{{message||state.error||'Serververbindung unterbrochen. Bike bei Bedarf direkt am Geräte-Cockpit bedienen.'}}</div>
  <div v-if="mode==='timeline'" class="fullscreen-timeline-content"><WorkoutTimeline :steps="steps" :elapsed="elapsed" :samples="samples" :power="measurement('power')" :heart-rate="measurement('heart_rate')" :live="online&&state.running&&!state.paused" :target="target||0" :control-events="state.control_events||[]" :offset="state.power_offset_watts||0" :limits="powerLimits" :preserve-aspect="true" :ftp="ftp"/></div>
  <div v-else class="fullscreen-metric-grid" aria-label="Alle Trainingskennzahlen"><article v-for="tile in tiles" :key="tile.key" class="fullscreen-metric" :data-metric="tile.key" :class="{'text-value':tile.text}" :title="tile.note"><span>{{tile.label}}</span><b>{{tile.value}} <small>{{tile.unit}}</small></b><p>{{tile.note}}</p></article></div>
  <div class="fullscreen-power-panel" :class="{expanded:controlsOpen}"><div class="fullscreen-power-summary"><button :aria-expanded="controlsOpen" aria-controls="fullscreen-watt-controls" @click="controlsOpen=!controlsOpen">Wattsteuerung <span aria-hidden="true">{{controlsOpen?'▾':'▴'}}</span></button><span><b>{{format(target)}} W angefordert</b> · {{controlLabel}}</span><small>{{confirmation}}</small></div>
   <div v-if="controlsOpen" id="fullscreen-watt-controls" class="fullscreen-watt-controls"><button class="fullscreen-watt-step" aria-label="Vollbild: Leistung um 10 Watt reduzieren" :disabled="manualLocked||target==null||target<=powerLimits.minimum" @click="power(target-10,'manual_button')">−10 W</button><label><span>Zielleistung · {{format(target)}} W</span><input aria-label="Vollbild: Zielleistung in Watt" type="range" :min="powerLimits.minimum" :max="powerLimits.maximum" :step="powerLimits.step" :value="target" :disabled="manualLocked" @input="power(Number($event.target.value),'manual_slider')"></label><button class="fullscreen-watt-step" aria-label="Vollbild: Leistung um 10 Watt erhöhen" :disabled="manualLocked||target==null||target>=powerLimits.maximum" @click="power(target+10,'manual_button')">+10 W</button><button class="fullscreen-return-plan" :disabled="manualLocked||!state.running||!state.steps?.length" @click="$emit('return-plan')">Zurück zum Trainingsplan</button></div>
  </div>
 </section>`
};
