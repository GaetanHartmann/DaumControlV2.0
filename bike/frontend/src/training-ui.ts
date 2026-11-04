import { computed, ref, watch } from 'vue';

export const WorkoutTimeline = {
 props: {steps:{default:()=>[]},elapsed:{default:0},samples:{default:()=>[]},power:{default:0},target:{default:0},ftp:{default:150}},
 setup(props:any){
  const timeOptions=[0,30,60,120,300,600], wattOptions=[0,25,50,100];
  const stored=(key:string,options:number[])=>{try{const value=Number(localStorage.getItem(key));return options.includes(value)?value:0;}catch{return 0;}};
  const timeGrid=ref(stored('studio-timeline-time-grid',timeOptions));
  const wattGrid=ref(stored('studio-timeline-watt-grid',wattOptions));
  watch(timeGrid,value=>{try{localStorage.setItem('studio-timeline-time-grid',String(value));}catch{}});
  watch(wattGrid,value=>{try{localStorage.setItem('studio-timeline-watt-grid',String(value));}catch{}});
  const total=computed(()=>props.steps.reduce((n:number,s:any)=>n+s.seconds,0)||Math.max(1800,Math.ceil(props.elapsed/600)*600));
  const maxW=computed(()=>Math.ceil(Math.max(100,props.target,...props.steps.map((s:any)=>s.watts),...props.samples.map((s:any)=>Math.max(s[1],s[2])))/50)*50+25);
  const timeInterval=computed(()=>timeGrid.value||timeOptions.slice(1).find(value=>total.value/value<=12)||Math.ceil(total.value/6000)*600);
  const wattInterval=computed(()=>wattGrid.value||(maxW.value>250?100:50));
  const timeTicks=computed(()=>Array.from({length:Math.floor(total.value/timeInterval.value)+1},(_,i)=>i*timeInterval.value));
  const wattTicks=computed(()=>Array.from({length:Math.floor(maxW.value/wattInterval.value)+1},(_,i)=>i*wattInterval.value));
  const timeLabels=computed(()=>{
   const spacing=Math.ceil(total.value/timeInterval.value/10);
   return [...timeTicks.value.filter((t,i)=>i%spacing===0&&total.value-t>=total.value*.06),total.value];
  });
  const formatDuration=(seconds:number)=>{const value=Math.round(seconds),minutes=Math.floor(value/60),rest=value%60;return minutes?`${minutes} min${rest?' '+rest+' s':''}`:`${rest} s`;};
  const formatTime=(seconds:number)=>{const value=Math.round(seconds);return value%60?`${Math.floor(value/60)}:${String(value%60).padStart(2,'0')}`:`${value/60}`;};
  const x=(t:number)=>46+Math.min(total.value,t)/total.value*806;
  const y=(w:number)=>205-Math.max(0,w)/maxW.value*153;
  const color=(watts:number)=>watts/props.ftp<.56?'#b6c4ad':watts/props.ftp<.76?'#8da982':watts/props.ftp<1?'#d1ae6c':'#d57e54';
  const blocks=computed(()=>{let t=0;return props.steps.map((s:any,i:number)=>{const from=t;t+=s.seconds;return {...s,from,to:t,x:x(from),width:x(t)-x(from),y:y(s.watts),color:color(s.watts),active:props.elapsed>=from&&props.elapsed<t,index:i};});});
  const line=(field:number)=>[...props.samples,[props.elapsed,props.power,props.target]].map((s:any)=>`${x(s[0])},${y(s[field])}`).join(' ');
  return {total,maxW,x,y,blocks,line,timeGrid,wattGrid,timeTicks,wattTicks,timeLabels,formatDuration,formatTime};
 },
 template:`<div class="workout-timeline">
  <div class="timeline-caption"><b>Dein Training auf einen Blick</b><span>Watt über Zeit · geplante Blöcke + Livewerte</span></div>
  <div class="timeline-grid-controls" role="group" aria-label="Zeitachsenraster einstellen">
   <label>Zeitraster<select aria-label="Zeitraster" v-model.number="timeGrid"><option :value="0">Automatisch</option><option :value="30">30 s</option><option :value="60">1 min</option><option :value="120">2 min</option><option :value="300">5 min</option><option :value="600">10 min</option></select></label>
   <label>Wattraster<select aria-label="Wattraster" v-model.number="wattGrid"><option :value="0">Automatisch</option><option :value="25">25 W</option><option :value="50">50 W</option><option :value="100">100 W</option></select></label>
  </div>
  <div class="timeline-chart-scroll" tabindex="0" role="region" aria-label="Zeitachse, horizontal scrollbar">
   <svg viewBox="0 0 900 250" role="img" aria-label="Trainings-Zeitachse mit Planleistung, tatsächlicher Leistung und aktueller Zeitposition">
    <g v-for="watts in wattTicks" :key="'w'+watts" class="watt-grid-line"><path :d="'M46 '+y(watts)+'H852'" stroke="#dfe7da" stroke-dasharray="4 6"/><text x="35" :y="y(watts)+4" text-anchor="end" class="axis-label">{{watts}}</text></g>
    <g v-for="seconds in timeTicks" :key="'t'+seconds" class="time-grid-line"><path :d="'M'+x(seconds)+' 45V205'" stroke="#dfe7da" stroke-dasharray="4 6"/></g>
    <g v-for="block in blocks" :key="block.index"><rect :x="block.x+1" :y="block.y" :width="Math.max(1,block.width-2)" :height="205-block.y" :fill="block.color" :opacity="block.active?.85:.45" rx="2"><title>{{block.name}} · {{block.watts}} W · {{formatDuration(block.seconds)}}</title></rect><text v-if="block.width>70" :x="block.x+block.width/2" :y="block.y-23" text-anchor="middle" class="block-label"><tspan :x="block.x+block.width/2">{{block.watts}} W</tspan><tspan :x="block.x+block.width/2" dy="14" class="block-duration">{{formatDuration(block.seconds)}}</tspan></text></g>
    <polyline :points="line(2)" fill="none" stroke="#2f634a" stroke-dasharray="5 4" stroke-width="2"/><polyline :points="line(1)" fill="none" stroke="#be633b" stroke-width="3"/>
    <path :d="'M'+x(elapsed)+' 32V210'" stroke="#244e39" stroke-width="2"/><circle :cx="x(elapsed)" cy="30" r="5" fill="#244e39"/><text :x="Math.min(815,Math.max(75,x(elapsed)))" y="18" text-anchor="middle" class="now-label">{{Math.floor(elapsed/60)}}:{{Math.floor(elapsed%60).toString().padStart(2,'0')}}</text>
    <g v-for="seconds in timeLabels" :key="seconds"><text :x="x(seconds)" y="232" text-anchor="middle" class="axis-label">{{formatTime(seconds)}}</text></g><text x="880" y="232" text-anchor="end" class="axis-label">min</text>
   </svg>
  </div>
  <div class="timeline-legend"><span><i class="planned"></i>Plan / Watt-Orientierung</span><span><i class="target"></i>Angelegtes Ziel</span><span><i class="actual"></i>Ist-Leistung</span></div>
  <div v-if="blocks.length" class="timeline-stages"><span>Dauer pro Leistungsstufe</span><ol tabindex="0" aria-label="Leistungsstufen mit Dauer"><li v-for="block in blocks" :key="block.index" :class="{active:block.active}" :aria-current="block.active?'step':undefined"><span>{{block.index+1}} · {{block.name}}</span><b>{{block.watts}} W · {{formatDuration(block.seconds)}}</b></li></ol></div>
 </div>`
};

export const PowerMountain = {
 props:{watts:{default:0},ftp:{default:150},steps:{default:()=>[]},elapsed:{default:0}},
 setup(props:any){
  const peak=computed(()=>210-Math.min(1.4,props.watts/props.ftp)*110);
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
  return {peak,points,terrain,route,grade};
 },
 template:`<div class="power-mountain"><div class="mountain-copy"><span>{{terrain?'DEINE VIRTUELLE BERGSTRECKE':'DEIN WATT-BERG'}}</span><h2>{{watts}} <small>Watt</small></h2><p v-if="terrain" class="terrain-grade">{{route.step?.name}} · {{grade>0?'+':''}}{{grade.toFixed(1)}} % virtuelle Steigung</p><p v-else>Mehr Leistung. Höherer Gipfel.</p></div><svg viewBox="0 0 900 350" role="img" :aria-label="terrain?'Virtuelles Streckenprofil mit Auffahrten, Abfahrten und aktueller Position':'Bergvisualisierung abhängig von der aktuellen Wattzahl'"><defs><linearGradient id="powerSky" x2="0" y2="1"><stop stop-color="#dce6d4"/><stop offset="1" stop-color="#eee4c6"/></linearGradient></defs><rect width="900" height="350" fill="url(#powerSky)"/><circle cx="740" cy="55" r="31" fill="#f6dca1"/><path d="M0 230L180 125 300 195 450 100 610 165 790 80 900 200V350H0Z" fill="#b2c1a7"/><g v-if="terrain"><polygon :points="'46,350 '+route.line+' 852,350'" fill="#507f62"/><polyline :points="route.line" fill="none" stroke="#ead5a8" stroke-width="6" stroke-linejoin="round"/><path :d="'M'+route.marker.x+' 40V'+route.marker.y" stroke="#244e39" stroke-dasharray="5 5" stroke-width="2"/><circle :cx="route.marker.x" :cy="route.marker.y" r="8" fill="#f28d4f" stroke="#fff9e9" stroke-width="3"/></g><g v-else><polygon :points="points" fill="#507f62"/><path :d="'M395 '+(peak+70)+'L485 '+peak+' 555 '+(peak+50)+' 510 '+(peak+35)+' 480 '+(peak+43)+' 457 '+(peak+35)+'Z'" fill="#e9eddf" opacity=".85"/><path d="M0 310Q220 220 400 290T900 275V350H0Z" fill="#214d3b"/><path :d="'M350 350Q590 240 485 '+(peak+15)" fill="none" stroke="#d8c39a" stroke-width="11" stroke-linecap="round"/></g></svg><small class="mountain-disclaimer">{{terrain?'Virtuelles Streckenprofil · Zeitverlauf, keine gemessenen Höhenmeter':'Visualisierung der Leistung · keine reale Steigung'}}</small></div>`
};
