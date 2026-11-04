"""Desktop shortcut: toggle the same setting as the DAUM Studio app."""
import json
import shutil
import subprocess
from urllib.request import Request, urlopen


def toggle():
    base = 'http://127.0.0.1:8000/api/power-settings'
    with urlopen(base, timeout=10) as response:
        settings = json.load(response)
    if not settings['available']:
        raise RuntimeError('Abschaltautomatik ist noch nicht installiert.')
    request = Request(base, data=json.dumps({'enabled': not settings['enabled']}).encode(),
                      headers={'Content-Type': 'application/json'}, method='POST')
    with urlopen(request, timeout=10) as response:
        settings = json.load(response)
    return 'EIN: Nach 5 Minuten ohne Daum-LAN wird heruntergefahren.' if settings['enabled'] else 'AUS: Der Pi bleibt eingeschaltet, auch ohne Daum.'


if __name__ == '__main__':
    try:
        message = toggle()
    except Exception as error:
        message = 'Umschalten fehlgeschlagen: ' + str(error)
    if shutil.which('notify-send'):
        subprocess.run(['notify-send', '-t', '8000', 'DAUM – Automatisch abschalten', message], check=False)
    else:
        # Raspberry Pi OS Lite + the existing desktop may lack notify-send.
        import gi
        gi.require_version('Gtk', '3.0')
        from gi.repository import Gtk
        dialog = Gtk.MessageDialog(message_type=Gtk.MessageType.INFO,
                                   buttons=Gtk.ButtonsType.OK,
                                   text='DAUM – Automatisch abschalten')
        dialog.format_secondary_text(message)
        dialog.run()
        dialog.destroy()
