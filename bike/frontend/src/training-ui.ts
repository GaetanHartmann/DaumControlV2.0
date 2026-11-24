import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import './timeline-responsive.css';

export const WorkoutTimeline = {
 props: {steps:{default:()=>[]},elapsed:{default:0},samples:{default:()=>[]},power:{default:null},heartRate:{default:null},live:{default:false},target:{default:0},ftp:{default:150},controlEvents:{default:()=>[]},offset:{default:0},limits:{default:()=>({minimum:0,maximum:1000})},preserveAspect:{default:false}},
 setup(props:any){
  const svgElement=ref<SVGSVGElement|null>(null),size=ref({width:900,height:250});
  let observer:ResizeObserver|undefined;
  function measure(){const bounds=svgElement.value?.getBoundingClientRect();if(bounds&&bounds.width>0&&bounds.height>0)size.value={width:Math.round(bounds.width*10)/10,height:Math.round(bounds.height*10)/10};}
  onMounted(()=>{measure();if(typeof ResizeObserver!=='undefined'){observer=new ResizeObserver(measure);if(svgElement.value)observer.observe(svgElement.value);}window.addEventListener('resize',measure);});
  onUnmounted(()=>{observer?.disconnect();window.removeEventListener('resize',measure);});
  const compact=computed(()=>size.value.width<620),short=computed(()=>size.value.height<155);
  const layout=computed(()=>({width:size.value.width,height:size.value.height,left:compact.value?36:44,right:size.value.width-(compact.value?12:22),top:short.value?22:45,bottom:size.value.height-(short.value?22:34)}));
  const plotWidth=computed(()=>Math.max(1,layout.value.right-layout.value.left));
  const plotHeight=computed(()=>Math.max(1,layout.value.bottom-layout.value.top));
  const timeOptions=[0,30,60,120,300,600], wattOptions=[0,25,50,100];
  const stored=(key:string,options:number[])=>{try{const value=Number(localStorage.getItem(key));return options.includes(value)?value:0;}catch{return 0;}};
  const timeGrid=ref(stored('studio-timeline-time-grid',timeOptions));
  const wattGrid=ref(stored('studio-timeline-watt-grid',wattOptions));
  const flag=(key:string)=>{try{return localStorage.getItem(key)==='true';}catch{return false;}};
  const markerPower=ref(flag('studio-marker-power')),markerPulse=ref(flag('studio-marker-pulse'));
  watch(markerPower,value=>{try{localStorage.setItem('studio-marker-power',String(value));}catch{}});
  watch(markerPulse,value=>{try{localStorage.setItem('studio-marker-pulse',String(value));}catch{}});
  watch(timeGrid,value=>{try{localStorage.setItem('studio-timeline-time-grid',String(value));}catch{}});
  watch(wattGrid,value=>{try{localStorage.setItem('studio-timeline-watt-grid',String(value));}catch{}});
  const total=computed(()=>props.steps.reduce((n:number,s:any)=>n+s.seconds,0)||Math.max(1800,Math.ceil(props.elapsed/600)*600));
  const maxW=computed(()=>{const values=[100,props.target,...props.steps.flatMap((s:any)=>[s.watts,Math.min(props.limits.maximum,Math.max(props.limits.minimum,s.watts+props.offset))]),...props.samples.flatMap((s:any)=>[s[1],s[2]])].filter((n:any)=>typeof n==='number'&&Number.isFinite(n));return Math.ceil(Math.max(...values)/50)*50+25;});
  const timeInterval=computed(()=>timeGrid.value||timeOptions.slice(1).find(value=>total.value/value<=Math.max(2,Math.floor(plotWidth.value/55)))||Math.ceil(total.value/Math.max(2,Math.floor(plotWidth.value/55))/600)*600);
  const wattInterval=computed(()=>wattGrid.value||[25,50,100,200,400,1000].find(value=>maxW.value/value<=Math.max(1,Math.floor(plotHeight.value/36)))||1000);
  const timeTicks=computed(()=>Array.from({length:Math.floor(total.value/timeInterval.value)+1},(_,i)=>i*timeInterval.value));
  const wattTicks=computed(()=>Array.from({length:Math.floor(maxW.value/wattInterval.value)+1},(_,i)=>i*wattInterval.value));
  const formatDuration=(seconds:number)=>{const value=Math.round(seconds),minutes=Math.floor(value/60),rest=value%60;return minutes?`${minutes} min${rest?' '+rest+' s':''}`:`${rest} s`;};
  const formatTime=(seconds:number)=>{const value=Math.round(seconds);return value%60?`${Math.floor(value/60)}:${String(value%60).padStart(2,'0')}`:`${value/60}`;};
  const x=(t:number)=>layout.value.left+Math.max(0,Math.min(total.value,t))/total.value*plotWidth.value;
  const y=(w:number)=>layout.value.bottom-Math.max(0,w)/maxW.value*plotHeight.value;
  const timeLabels=computed(()=>{
   const values:number[]=[];
   for(const t of timeTicks.value){if(t>=total.value)continue;if(!values.length||x(t)-x(values.at(-1)!)>=64)values.push(t);}
   const endpointWidth=(formatTime(total.value).length+4)*6;
   while(values.length>1&&x(total.value)-x(values.at(-1)!)<endpointWidth+10)values.pop();
   return [...values,total.value];
  });
  const wattLabels=computed(()=>{if(short.value)return [0];let previous=Infinity;return wattTicks.value.filter(w=>{const position=y(w);if(previous-position<30)return false;previous=position;return true;});});
  const gridOpacity=(seconds:number)=>timeInterval.value/total.value*plotWidth.value<12&&Math.round(seconds/timeInterval.value)%Math.ceil(12/(timeInterval.value/total.value*plotWidth.value))!==0?.18:1;
  const color=(watts:number)=>watts/props.ftp<.56?'#b6c4ad':watts/props.ftp<.76?'#8da982':watts/props.ftp<1?'#d1ae6c':'#d57e54';
  const blocks=computed(()=>{let t=0;return props.steps.map((s:any,i:number)=>{const from=t;t+=s.seconds;const left=x(from),width=x(t)-left,top=y(s.watts),adjustedWatts=Math.min(props.limits.maximum,Math.max(props.limits.minimum,s.watts+props.offset)),adjustedY=y(adjustedWatts);return {...s,from,to:t,x:left,width,y:top,color:color(s.watts),adjustedWatts,adjustedY,adjustedColor:color(adjustedWatts),limited:adjustedWatts!==s.watts+props.offset,active:props.elapsed>=from&&props.elapsed<t,index:i,showLabel:!short.value&&width>=82&&layout.value.bottom-(props.offset?adjustedY:top)>=(props.offset?54:38)};});});
  const selectedIndex=ref<number|null>(null);
  watch(()=>props.steps.map((step:any)=>[step.name,step.seconds,step.watts].join(':')).join('|'),()=>selectedIndex.value=null);
  const selectedStep=computed(()=>selectedIndex.value==null?null:blocks.value[selectedIndex.value]||null);
  function selectBlock(index:number){selectedIndex.value=index;}
  function selectAt(event:PointerEvent){
   if(!blocks.value.length||!svgElement.value)return;
   const bounds=svgElement.value.getBoundingClientRect(),position=Math.max(0,Math.min(total.value,(event.clientX-bounds.left-layout.value.left)/plotWidth.value*total.value));
   const index=blocks.value.findIndex((block:any)=>position>=block.from&&position<block.to);
   selectBlock(index<0?blocks.value.length-1:index);
  }
  function adjacent(direction:number){if(!blocks.value.length)return;selectBlock(Math.max(0,Math.min(blocks.value.length-1,(selectedIndex.value??0)+direction)));}
  const manualEvents=computed(()=>props.controlEvents.filter((e:any)=>e.event==='requested'&&(e.source==='manual_slider'||e.source==='manual_button')&&Number.isFinite(e.elapsed_seconds)));
  const line=(field:number)=>{let drawing=false;return [...props.samples,...(props.live?[[props.elapsed,props.power,props.target]]:[])].map((s:any)=>{if(s[field]==null||!Number.isFinite(s[field])){drawing=false;return '';}const segment=(drawing?'L':'M')+x(s[0])+','+y(s[field]);drawing=true;return segment;}).join(' ');};
  const markerX=computed(()=>Math.max(layout.value.left+27,Math.min(layout.value.right-27,x(props.elapsed))));
  const badgeX=computed(()=>Math.max(layout.value.left,Math.min(layout.value.right-90,x(props.elapsed)-45)));
  return {svgElement,size,layout,compact,short,total,maxW,x,y,blocks,line,manualEvents,timeGrid,wattGrid,markerPower,markerPulse,timeTicks,wattTicks,timeLabels,wattLabels,formatDuration,formatTime,markerX,badgeX,gridOpacity,selectedStep,selectedIndex,selectBlock,selectAt,adjacent};
 },
 template:`<div class="workout-timeline responsive-timeline" :class="{'timeline-compact':compact,'timeline-short':short}" :data-responsive-mode="compact?'compact':'wide'" :data-chart-width="size.width" :data-chart-height="size.height">
  <div class="timeline-caption"><b>Dein Training auf einen Blick</b><span>Watt über Zeit · geplante Blöcke + Livewerte</span></div>
  <div class="timeline-grid-controls" role="group" aria-label="Zeitachsenraster einstellen">
   <label>Zeitraster<select aria-label="Zeitraster" v-model.number="timeGrid"><option :value="0">Automatisch</option><option :value="30">30 s</option><option :value="60">1 min</option><option :value="120">2 min</option><option :value="300">5 min</option><option :value="600">10 min</option></select></label>
   <label>Wattraster<select aria-label="Wattraster" v-model.number="wattGrid"><option :value="0">Automatisch</option><option :value="25">25 W</option><option :value="50">50 W</option><option :value="100">100 W</option></select></label>
   <label><input type="checkbox" v-model="markerPower">Watt am Zeitmarker</label><label><input type="checkbox" v-model="markerPulse">Puls am Zeitmarker</label>
  </div>
  <div class="timeline-chart-scroll" tabindex="0" role="region" aria-label="Zeitachse, an Bildschirmbreite angepasst">
   <svg ref="svgElement" :viewBox="'0 0 '+size.width+' '+size.height" preserveAspectRatio="none" role="img" aria-label="Trainings-Zeitachse mit Planleistung, tatsächlicher Leistung und aktueller Zeitposition" @pointerup="selectAt">
    <g v-for="watts in wattTicks" :key="'w'+watts" class="watt-grid-line"><path :d="'M'+layout.left+' '+y(watts)+'H'+layout.right" stroke="#dfe7da" stroke-dasharray="4 6"/><text v-if="wattLabels.includes(watts)" :x="layout.left-8" :y="y(watts)+4" text-anchor="end" class="axis-label watt-axis-label">{{watts}}</text></g>
    <g v-for="seconds in timeTicks" :key="'t'+seconds" class="time-grid-line"><path :d="'M'+x(seconds)+' '+layout.top+'V'+layout.bottom" :opacity="gridOpacity(seconds)" stroke="#dfe7da" stroke-dasharray="4 6"/></g>
    <g v-for="block in blocks" :key="block.index"><rect :data-segment-index="block.index" :x="block.x+.5" :y="block.y" :width="Math.max(.5,block.width-1)" :height="layout.bottom-block.y" :fill="block.color" :opacity="offset?.16:block.active?.85:.5" :stroke="selectedIndex===block.index?'#244e39':offset?'#92a18a':'none'" stroke-width="2" rx="2"><title>{{block.name}} · {{block.watts}} W · {{formatDuration(block.seconds)}}</title></rect></g>
    <g v-if="offset" v-for="block in blocks" :key="'offset'+block.index"><rect class="adjusted-segment" :data-adjusted-segment-index="block.index" :data-adjusted-watts="block.adjustedWatts" :x="block.x+.5" :y="block.adjustedY" :width="Math.max(.5,block.width-1)" :height="layout.bottom-block.adjustedY" :fill="block.adjustedColor" :opacity="block.active?.8:.55" rx="2"><title>{{block.name}} · angepasst {{block.adjustedWatts}} W · Originalplan {{block.watts}} W · {{formatDuration(block.seconds)}}</title></rect><path :d="'M'+block.x+' '+block.adjustedY+'h'+block.width" stroke="#2f634a" stroke-width="3" stroke-dasharray="6 4"/></g>
    <path :d="line(2)" fill="none" stroke="#2f634a" stroke-dasharray="5 4" stroke-width="2"/><path :d="line(1)" fill="none" stroke="#be633b" stroke-width="3"/>
    <g v-for="block in blocks" :key="'label'+block.index"><text v-if="block.showLabel" :x="block.x+block.width/2" :y="(offset?block.adjustedY:block.y)+16" text-anchor="middle" class="block-label"><tspan :x="block.x+block.width/2">{{offset?block.adjustedWatts:block.watts}} W</tspan><tspan v-if="offset" :x="block.x+block.width/2" dy="15" class="block-original">Plan {{block.watts}} W</tspan><tspan :x="block.x+block.width/2" dy="15" class="block-duration">{{formatDuration(block.seconds)}}</tspan></text></g>
    <g v-for="(event,index) in manualEvents" :key="'manual'+index" class="manual-event-marker"><path :d="'M'+x(event.elapsed_seconds)+' '+layout.top+'V'+layout.bottom" stroke="#b47b2f" stroke-dasharray="2 5" opacity=".55"/><circle :cx="x(event.elapsed_seconds)" :cy="y(event.requested_target_watts)" r="4" fill="#b47b2f"><title>Manuell · {{event.requested_target_watts}} W bei {{formatTime(event.elapsed_seconds)}}</title></circle></g>
    <text v-if="short&&!wattLabels.includes(maxW)" :x="layout.left-8" :y="layout.top+4" text-anchor="end" class="axis-label watt-axis-label">{{maxW}}</text>
    <path :d="'M'+x(elapsed)+' '+(short?18:layout.top-13)+'V'+(layout.bottom+4)" stroke="#244e39" stroke-width="2"/><circle :cx="x(elapsed)" :cy="short?18:layout.top-15" r="4" fill="#244e39"/><text :x="markerX" :y="short?12:layout.top-25" text-anchor="middle" class="now-label">{{Math.floor(elapsed/60)}}:{{Math.floor(elapsed%60).toString().padStart(2,'0')}}</text>
    <g v-if="(markerPower||markerPulse)&&!short" class="marker-values" :transform="'translate('+badgeX+','+(layout.top+4)+')'"><rect width="90" :height="markerPower&&markerPulse?40:23" rx="4" fill="#fffef4" stroke="#9bb28c"/><text v-if="markerPower" x="45" y="16" text-anchor="middle">{{live&&power!=null?power+' W':'W: —'}}</text><text v-if="markerPulse" x="45" :y="markerPower?33:16" text-anchor="middle">{{live&&heartRate!=null?heartRate+' bpm':'Puls: —'}}</text></g>
    <g v-for="seconds in timeLabels" :key="seconds"><text :x="x(seconds)" :y="short?layout.height-5:layout.bottom+22" :text-anchor="seconds===total?'end':seconds===0?'start':'middle'" class="axis-label time-axis-label">{{formatTime(seconds)}}{{seconds===total?' min':''}}</text></g>
   </svg>
  </div>
  <div v-if="selectedStep" class="timeline-selected-step" role="status" aria-live="polite"><button type="button" aria-label="Vorherige Leistungsstufe" :disabled="selectedIndex===0" @click="adjacent(-1)">‹</button><div><span>Stufe {{selectedIndex+1}} / {{blocks.length}} · {{selectedStep.name}}</span><b>{{offset?selectedStep.adjustedWatts:selectedStep.watts}} W · {{formatDuration(selectedStep.seconds)}}</b><small v-if="offset">Originalplan {{selectedStep.watts}} W · Plan {{offset>0?'+':''}}{{offset}} W{{selectedStep.limited?' · an Grenze begrenzt':''}}</small></div><button type="button" aria-label="Nächste Leistungsstufe" :disabled="selectedIndex===blocks.length-1" @click="adjacent(1)">›</button><button type="button" aria-label="Stufendetails schließen" @click="selectedIndex=null">×</button></div>
  <div class="timeline-legend"><span><i class="planned"></i>Ursprünglicher Plan</span><span v-if="offset"><i class="adjusted"></i>Angepasster Plan {{offset>0?'+':''}}{{offset}} W</span><span><i class="target"></i>Angeforderter Sollwert</span><span><i class="actual"></i>Gemessene Leistung</span></div>
  <div v-if="blocks.length" class="timeline-stages"><span>Dauer pro Leistungsstufe</span><ol tabindex="0" aria-label="Leistungsstufen mit Dauer"><li v-for="block in blocks" :key="block.index" :class="{active:block.active,selected:selectedIndex===block.index}" :aria-current="block.active?'step':undefined"><button type="button" :aria-pressed="selectedIndex===block.index" @click="selectBlock(block.index)"><span>{{block.index+1}} · {{block.name}}</span><b>{{offset?block.adjustedWatts:block.watts}} W · {{formatDuration(block.seconds)}}</b><small v-if="offset">Originalplan {{block.watts}} W</small></button></li></ol></div>
 </div>`
};

export const PowerMountain = {
 props:{watts:{default:null},sourceLabel:{default:'Watt-Vorschau'},ftp:{default:150},steps:{default:()=>[]},elapsed:{default:0}},
 setup(props:any){
  const available=computed(()=>props.watts!==null&&Number.isFinite(props.watts));
  const peak=computed(()=>available.value?210-Math.min(1.4,props.watts/props.ftp)*110:210);
  const points=computed(()=>`0,270 170,220 315,245 485,${peak.value} 620,190 760,150 900,260 900,350 0,350`);
  const terrain=computed(()=>props.steps.some((s:any)=>s.grade_percent!==undefined));
  const route=computed(()=>{
   let seconds=0,height=0;
   const nodes=[{seconds:0,height:0}];
   for(const step of props.steps){seconds+=step.seconds;height+=(step.grade_percent||0)*step.seconds;nodes.push({seconds,height});}
   const low=Math.min(...nodes.map(n=>n.height)),high=Math.max(...nodes.map(n=>n.height));
   const project=(node:any)=>({x:46+node.seconds/(seconds||1)*806,y:260-(node.height-low)/(high-low||1)*155});
   const projected=nodes.map(project),position=Math.max(0,Math.min(seconds,props.elapsed));
   let index=nodes.findIndex(n=>n.seconds>position)-1;
   if(index<0)index=props.steps.length-1;
   const from=nodes[Math.max(0,index)],to=nodes[Math.min(nodes.length-1,index+1)];
   const fraction=(position-from.seconds)/(to.seconds-from.seconds||1);
   const marker=project({seconds:position,height:from.height+(to.height-from.height)*fraction});
   return {line:projected.map(n=>`${n.x},${n.y}`).join(' '),marker,step:props.steps[Math.max(0,index)]};
  });
  const grade=computed(()=>Number(route.value.step?.grade_percent||0));
  return {peak,points,terrain,route,grade,available};
 },
 template:`<div class="power-mountain"><div class="mountain-copy"><span>{{terrain?'DEINE VIRTUELLE BERGSTRECKE':sourceLabel}}</span><h2>{{available?watts:'—'}} <small>Watt</small></h2><p v-if="terrain" class="terrain-grade">{{route.step?.name}} · {{grade>0?'+':''}}{{grade.toFixed(1)}} % virtuelle Steigung</p><p v-else>{{available?'Watt-Vorschau · keine reale Höhe':'Keine verifizierte Ist-Leistung verfügbar.'}}</p></div><svg viewBox="0 0 900 350" role="img" :aria-label="terrain?'Virtuelles Streckenprofil mit Auffahrten, Abfahrten und aktueller Position':'Bergvisualisierung abhängig von der aktuellen Wattzahl'"><defs><linearGradient id="powerSky" x2="0" y2="1"><stop stop-color="#dce6d4"/><stop offset="1" stop-color="#eee4c6"/></linearGradient></defs><rect width="900" height="350" fill="url(#powerSky)"/><circle cx="740" cy="55" r="31" fill="#f6dca1"/><path d="M0 230L180 125 300 195 450 100 610 165 790 80 900 200V350H0Z" fill="#b2c1a7"/><g v-if="terrain"><polygon :points="'46,350 '+route.line+' 852,350'" fill="#507f62"/><polyline :points="route.line" fill="none" stroke="#ead5a8" stroke-width="6" stroke-linejoin="round"/><path :d="'M'+route.marker.x+' 40V'+route.marker.y" stroke="#244e39" stroke-dasharray="5 5" stroke-width="2"/><circle :cx="route.marker.x" :cy="route.marker.y" r="8" fill="#f28d4f" stroke="#fff9e9" stroke-width="3"/></g><g v-else-if="available"><polygon :points="points" fill="#507f62"/><path :d="'M395 '+(peak+70)+'L485 '+peak+' 555 '+(peak+50)+' 510 '+(peak+35)+' 480 '+(peak+43)+' 457 '+(peak+35)+'Z'" fill="#e9eddf" opacity=".85"/><path d="M0 310Q220 220 400 290T900 275V350H0Z" fill="#214d3b"/><path :d="'M350 350Q590 240 485 '+(peak+15)" fill="none" stroke="#d8c39a" stroke-width="11" stroke-linecap="round"/></g></svg><small class="mountain-disclaimer">{{terrain?'Virtuelles Streckenprofil · Zeitverlauf, keine gemessenen Höhenmeter':'Visualisierung der Leistung · keine reale Steigung'}}</small></div>`
};
