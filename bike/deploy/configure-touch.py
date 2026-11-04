from pathlib import Path
from datetime import datetime
path = Path('/boot/firmware/config.txt')
text = path.read_text()
marker = '# DAUM Studio GPIO touch'
if marker not in text:
    backup = path.with_name('config.txt.before-daum-touch-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    backup.write_text(text)
    text += '\n[all]\n' + marker + '\ndtparam=spi=on\ndtoverlay=ads7846,cs=1,penirq=25,penirq_pull=2,speed=50000,xohms=150,pmax=255,xmin=200,xmax=3900,ymin=200,ymax=3900\n'
    path.write_text(text)
    print('Gespeichert. Sicherung:', backup)
else:
    print('Touch-Konfiguration ist bereits gespeichert.')
