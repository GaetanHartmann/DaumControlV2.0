"""Black Wayland overlay; HDMI stays active and the waking tap is consumed.

No lock or idle inhibitor. SIGUSR1 requests wake, after held input releases.
"""
import os
from pathlib import Path
import signal
import time

vendor = Path(__file__).resolve().parent / 'vendor/usr/lib'
typelibs = list(vendor.glob('*/girepository-1.0'))
if typelibs:
    os.environ['GI_TYPELIB_PATH'] = os.pathsep.join([str(path) for path in typelibs] + [os.environ.get('GI_TYPELIB_PATH', '')])
os.environ['GDK_BACKEND'] = 'wayland'

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('GtkLayerShell', '0.1')
from gi.repository import Gdk, GLib, Gtk, GtkLayerShell


class BlackOverlay:
    def __init__(self):
        if not GtkLayerShell.is_supported():
            raise RuntimeError('Wayland layer shell is unavailable')
        self.window = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        self.window.set_title('DAUM display saver')
        self.window.set_decorated(False)
        style = Gtk.CssProvider()
        style.load_from_data(b'window { background-color: #000; background-image: none; }')
        self.window.get_style_context().add_provider(style, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        GtkLayerShell.init_for_window(self.window)
        GtkLayerShell.set_namespace(self.window, 'daum-display-saver')
        GtkLayerShell.set_layer(self.window, GtkLayerShell.Layer.OVERLAY)
        GtkLayerShell.set_exclusive_zone(self.window, -1)
        GtkLayerShell.set_keyboard_mode(self.window, GtkLayerShell.KeyboardMode.EXCLUSIVE)
        for edge in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM, GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT):
            GtkLayerShell.set_anchor(self.window, edge, True)
        self.window.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK |
                               Gdk.EventMask.KEY_PRESS_MASK | Gdk.EventMask.KEY_RELEASE_MASK |
                               Gdk.EventMask.POINTER_MOTION_MASK | Gdk.EventMask.SCROLL_MASK |
                               Gdk.EventMask.TOUCH_MASK)
        self.buttons, self.keys, self.touches = set(), set(), 0
        self.wake_at = None
        self.last_input = time.monotonic()
        self.ready = Path(os.environ['XDG_RUNTIME_DIR']) / 'daum-display-saver.ready'
        self.window.connect('event', self.input_event)
        self.window.connect('map-event', self.mapped)
        self.window.connect('destroy', lambda *_: Gtk.main_quit())
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGUSR1, self.wake)
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self.stop)
        GLib.timeout_add(25, self.check_wake)

    def mapped(self, *_):
        self.window.get_window().set_cursor(Gdk.Cursor.new_for_display(self.window.get_display(), Gdk.CursorType.BLANK_CURSOR))
        self.ready.write_text(str(os.getpid()), encoding='ascii')
        print('Black overlay mapped; HDMI stays active', flush=True)
        return False

    def wake(self, *_):
        if self.wake_at is None:
            self.wake_at = time.monotonic() + .4
        return True

    def stop(self, *_):
        self.window.destroy()
        return False

    def input_event(self, _, event):
        kind = event.type
        if kind == Gdk.EventType.BUTTON_PRESS:
            self.buttons.add(event.get_button()[1])
        elif kind == Gdk.EventType.BUTTON_RELEASE:
            self.buttons.discard(event.get_button()[1])
        elif kind == Gdk.EventType.KEY_PRESS:
            self.keys.add(event.get_keycode()[1])
        elif kind == Gdk.EventType.KEY_RELEASE:
            self.keys.discard(event.get_keycode()[1])
        elif kind == Gdk.EventType.TOUCH_BEGIN:
            self.touches += 1
        elif kind in (Gdk.EventType.TOUCH_END, Gdk.EventType.TOUCH_CANCEL):
            self.touches = max(0, self.touches - 1)
        elif kind not in (Gdk.EventType.MOTION_NOTIFY, Gdk.EventType.SCROLL):
            return False
        self.last_input = time.monotonic()
        self.wake()
        return True

    def check_wake(self):
        now = time.monotonic()
        if self.wake_at is not None and now >= self.wake_at and now - self.last_input >= .15 and not (self.buttons or self.keys or self.touches):
            print('Wake input released; removing black overlay', flush=True)
            self.window.destroy()
            return False
        return True

    def run(self):
        try:
            self.window.show_all()
            Gtk.main()
        finally:
            self.ready.unlink(missing_ok=True)


if __name__ == '__main__':
    BlackOverlay().run()
