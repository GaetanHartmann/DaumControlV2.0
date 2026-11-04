from pathlib import Path
p=Path(__file__).parents[1]/'frontend'/'src'/'main.ts'
s=p.read_text(encoding='utf-8-sig')
s=s.replace("(s.watts*intensity.value/100)","(s.watts*(selectedPlan.value?.meta?.calibration?100:intensity.value)/100)")
s=s.replace('intensity_percent:Number(intensity.value)','intensity_percent:selectedPlan.value?.meta?.calibration?100:Number(intensity.value)')
s=s.replace('Watt-Intensität · {{intensity}} %','Watt-Intensität · {{selectedPlan.meta?.calibration?100:intensity}} %')
s=s.replace(':disabled="state.running||trainingMode===\'hr\'"',':disabled="state.running||trainingMode===\'hr\'||selectedPlan.meta?.calibration"')

calibration='''
    <section v-if="state.calibrating&&state.running" class="calibration-live card"><div><p class="eyebrow">ORIENTIERUNG · KEIN MAXIMALTEST</p><h3>Wie fühlt sich diese Stufe an?</h3><p>Nach mindestens einer Minute gleichmäßigem Treten: Kannst du entspannt ganze Sätze sprechen? Nur dann als lockere Ausgangsleistung markieren. Nicht bis zur Erschöpfung fahren.</p><small>{{profile.comfortable_watts?'Zuletzt als locker markiert: '+profile.comfortable_watts+' W. Das ist keine FTP.':'Noch keine Stufe eingeordnet. Es wird kein Wert automatisch als FTP oder HFmax gespeichert.'}}</small></div><div class="calibration-actions"><button class="button secondary" :disabled="busy||state.paused||state.mode==='demo'" @click="action('calibration/comfortable')">Gut sprechbar · diese Wattstufe merken</button><button class="button stop" :disabled="busy" @click="action('stop')">Zu anstrengend · beenden</button></div></section>
'''
s=s.replace('    <div class="dashboard-grid">',calibration+'    <div class="dashboard-grid">',1)

start=s.index('   <template v-if="tab===\'Aktivitäten\'">')
end=s.index('   <footer>',start)
s=s[:start]+'''   <template v-if="tab==='Aktivitäten'"><section class="card activity-card"><div class="section-title"><h2>Deine letzten Rides</h2><button class="button secondary" @click="modal='export'"><Download :size="16"/>Apple Health &amp; Export</button></div><p v-if="!rides.length">Dein erster Ride wartet. Beendete Trainings werden hier gespeichert.</p><div class="activity-row" v-for="ride in rides" :key="ride.id"><span class="connection-icon"><Bike/></span><div><b>{{ride.mode==='demo'?'Demo · ':''}}{{ride.plan_name||'Daum-Ride'}}</b><p>{{new Date((ride.started_at||ride.created.replace(' ','T')+'Z')).toLocaleString('de-DE')}} · {{ride.training_mode==='hr'?'Pulsgeführt':'Watt / Zwift'}}</p></div><b>{{clock(ride.seconds)}}</b><b>{{ride.distance.toFixed(2)}} km</b><span>{{Math.round(ride.energy)}} kJ</span><div class="ride-exports"><a v-for="format in ['tcx','csv','json']" class="button secondary" :href="'/api/rides/'+ride.id+'/export/'+format" :download="'DAUM-Studio-'+ride.id+'.'+format" :aria-label="format.toUpperCase()+' für Fahrt '+ride.id+' herunterladen'"><Download :size="13"/>{{format.toUpperCase()}}</a></div></div><p class="export-note">Neue Fahrten enthalten die aufgezeichnete Messspur; ältere Fahrten gegebenenfalls nur eine Zusammenfassung. Demo-Dateien sind gekennzeichnet. Mechanische kJ sind keine gemessenen Kalorien.</p></section></template>
'''+s[end:]

iphone_card='''<article class="card connection"><span class="connection-icon"><Smartphone/></span><div><h2>iPhone als Trainingsbedienung</h2><p>Safari über WLAN · Livewerte und dieselbe zentrale Steuerung</p><small>Für Zwift auf dem iPhone zusätzlich „DAUM Studio“ per Bluetooth auswählen.</small></div><button class="button secondary" @click="modal='iphone'">iPhone verbinden</button></article>'''
s=s.replace('<div class="connections"><article','<div class="connections">'+iphone_card+'<article',1)

modals='''
   <template v-if="modal==='iphone'"><span class="eyebrow">DEIN MOBILES COCKPIT</span><h2>iPhone verbinden</h2><p>1. iPhone und Pi im selben WLAN verbinden.<br>2. In Safari diese Adresse öffnen:</p><a class="phone-address" :href="appUrl">{{appUrl}}</a><p>3. In Safari auf „Teilen“ → „Zum Home-Bildschirm“ tippen. Damit öffnest du die Trainingsseite künftig direkt über ihr Symbol.</p><p>Du steuerst damit dieselbe Fahrt wie am Pi-Display. Für Zwift auf dem iPhone: Bluetooth aktivieren und DAUM Studio als Leistungsquelle und steuerbaren Trainer wählen.</p><button class="button secondary" @click="modal='export'">Export &amp; Apple Health ansehen</button></template>
   <template v-if="modal==='export'"><span class="eyebrow">DEIN TRAINING MITNEHMEN</span><h2>Export &amp; Apple Health</h2><p><b>TCX:</b> Trainingsdatei mit Zeit, Strecke und den verfügbaren Leistungs-, Kadenz- und Pulswerten. Geeignet für kompatible Trainingsplattformen, z. B. den Datei-Upload von Strava.</p><p><b>CSV / JSON:</b> Zusammenfassung und Messspur für eigene Auswertungen. Fehlende Werte bleiben leer. Demo-Fahrten bleiben als simuliert gekennzeichnet.</p><p><b>Apple Health:</b> Noch keine direkte HealthKit-Synchronisation. Die Pi-Webseite kann keine HealthKit-Berechtigung auf deinem iPhone anfordern. Du brauchst dafür eine iPhone-App, die Trainingsdateien importiert und die Schreibberechtigung für Health besitzt; die Unterstützung hängt von dieser App ab.</p><p>Auf dem iPhone: TCX bei der Fahrt herunterladen, in „Dateien“ speichern und über „Teilen“ an eine passende Import-App übergeben. Apple Health selbst wird hier nicht als TCX-Importziel angeboten.</p><p>Kalorien werden nicht aus mechanischen kJ erfunden. Das TCX-Pflichtfeld „Calories“ enthält 0 mit entsprechendem Hinweis. VO₂max wird weder berechnet noch exportiert.</p><p class="source-links"><a href="https://developer.apple.com/documentation/healthkit/authorizing-access-to-health-data" target="_blank" rel="noopener">Apple · HealthKit-Berechtigung ↗</a><a href="https://support.strava.com/en-us/articles/15402066-how-do-i-get-my-activities-to-strava" target="_blank" rel="noopener">Strava · Datei-Upload ↗</a></p></template>
'''
s=s.replace("   <template v-if=\"modal==='profile'\">",modals+"   <template v-if=\"modal==='profile'\">")
p.write_text(s,encoding='utf-8')

index=p.parents[1]/'index.html'
html=index.read_text()
html=html.replace('<meta name="theme-color"','<meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-title" content="DAUM Studio"><meta name="theme-color"')
index.write_text(html)
