import './timeline-power-controls.css';

/** Small direct controls; all requests still use the cockpit's single queue. */
export const TimelinePowerControls = {
 props:{target:{default:null},powerLimits:{default:()=>({minimum:25,maximum:400,step:5})},locked:{default:false},controlMode:{default:'plan'},offset:{default:null}},
 emits:['power'],
 setup(props:any,{emit}:any){
  const adjust=(delta:number)=>{
   if(props.locked||props.target==null||!Number.isFinite(Number(props.target)))return;
   emit('power',Math.max(props.powerLimits.minimum,Math.min(props.powerLimits.maximum,Number(props.target)+delta)),'manual_button');
  };
  return {adjust};
 },
 template:`<div class="timeline-power-controls" role="group" aria-label="Leistung direkt an der Zeitachse anpassen">
  <button type="button" aria-label="Zeitachse: Leistung um 10 Watt reduzieren" :disabled="locked||target==null||target<=powerLimits.minimum" @click="adjust(-10)">−10 W</button>
  <span class="timeline-watt-value" title="Sollwert angefordert" aria-live="polite"><b>{{target==null?'—':target}} <small>W</small></b><small>{{offset!=null?'Plan '+(offset>=0?'+':'')+offset+' W':controlMode==='manual_override'?'Manuell':controlMode==='hr'?'Puls':'Plan'}}</small></span>
  <button type="button" aria-label="Zeitachse: Leistung um 10 Watt erhöhen" :disabled="locked||target==null||target>=powerLimits.maximum" @click="adjust(10)">+10 W</button>
 </div>`
};
