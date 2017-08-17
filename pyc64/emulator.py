"""
'fast' Commodore-64 'emulator' in 100% pure Python 3.x :)

This module is the GUI window logic, handling keyboard input
and screen drawing via tkinter bitmaps.

Written by Irmen de Jong (irmen@razorvine.net)
License: MIT open-source.
"""

import io
import os
import tkinter
import pkgutil
from PIL import Image, ImageDraw
from .memory import ScreenAndMemory, colorpalette
from .basic import BasicInterpreter, ResetMachineException, HandleBufferedKeysException
from .python import PythonInterpreter


class EmulatorWindow(tkinter.Tk):
    temp_graphics_folder = "temp_gfx"

    def __init__(self, title):
        super().__init__()
        self.wm_title(title)
        self.appicon = tkinter.PhotoImage(data=pkgutil.get_data(__name__, "icon.gif"))
        self.wm_iconphoto(self, self.appicon)
        self.geometry("+200+100")
        self.screen = ScreenAndMemory()
        self.repaint_only_dirty = True     # set to False if you're continuously changing most of the screen
        self._cyclic_interpret_after = None
        self.switch_interpreter("basic")
        self.canvas = tkinter.Canvas(self, width=128 + 40 * 16, height=128 + 25 * 16, borderwidth=0, highlightthickness=0)
        self.buttonbar = tkinter.Frame(self)
        resetbut = tkinter.Button(self.buttonbar, text="reset", command=self.reset_machine)
        resetbut.pack(side=tkinter.LEFT)
        self.buttonbar.pack(fill=tkinter.X)
        topleft = self.screencor((0, 0))
        botright = self.screencor((40, 25))
        self.screenrect = self.canvas.create_rectangle(topleft[0], topleft[1], botright[0], botright[1], outline="")
        self.create_bitmaps()
        # create the 1000 character bitmaps fixed on the canvas:
        self.charbitmaps = []
        for y in range(25):
            for x in range(40):
                cor = self.screencor((x, y))
                bm = self.canvas.create_bitmap(cor[0], cor[1], bitmap="@"+self.temp_graphics_folder+"/char-20.xbm",
                                               foreground="black", background="white", anchor=tkinter.NW, tags="charbitmap")
                self.charbitmaps.append(bm)
        # create the 8 sprite bitmaps:
        self.spritebitmaps = []
        for i in range(7, -1, -1):
            cor = self.screencor_sprite((30 + i * 20, 140 + i * 10))
            bm = self.canvas.create_bitmap(cor[0], cor[1], bitmap="@{:s}/sprite-{:d}.xbm".format(self.temp_graphics_folder, i),
                                           foreground=self.tkcolor(i+8), background=None, anchor=tkinter.NW, tags="spritebitmap")
            self.spritebitmaps.insert(0, bm)
        # the borders:
        self.border1 = self.canvas.create_rectangle(0, 0, 128 + 40 * 16, 64, outline="", fill="#000")
        self.border2 = self.canvas.create_rectangle(64 + 40 * 16, 64, 128 + 40 * 16, 64 + 25 * 16, outline="", fill="#000")
        self.border3 = self.canvas.create_rectangle(0, 64 + 25 * 16, 128 + 40 * 16, 128 + 25 * 16, outline="", fill="#000")
        self.border4 = self.canvas.create_rectangle(0, 64, 64, 64 + 25 * 16, outline="", fill="#000")
        self.bind("<KeyPress>", lambda event: self.keypress(*self._keyevent(event)))
        self.bind("<KeyRelease>", lambda event: self.keyrelease(*self._keyevent(event)))
        self.repaint()
        self.canvas.pack()
        self._cyclic_blink_cursor()
        self._cyclic_repaint()
        introtxt = self.canvas.create_text(topleft[0] + 320, topleft[0] + 180,
                                           text="pyc64 basic & function keys active\n\nuse 'gopy' to enter Python mode", fill="white")
        self.after(2500, lambda: self.canvas.delete(introtxt))
        self._cyclic_interpret_after = self.after(10, self.basic_interpret_loop)

    def _cyclic_blink_cursor(self):
        self.screen.blink_cursor()
        self.cyclic_blink_after = self.after(self.screen.cursor_blink_rate, self._cyclic_blink_cursor)

    def _cyclic_repaint(self):
        self.repaint()
        self.cyclic_repaint_after = self.after(self.screen.update_rate, self._cyclic_repaint)

    def _keyevent(self, event):
        c = event.char
        if not c or ord(c) > 255:
            c = event.keysym
        return c, event.state, event.x, event.y

    def keypress(self, char, state, mousex, mousey):
        # print("keypress", repr(char), state)  # XXX
        with_shift = state & 1
        with_control = state & 4
        with_alt = state & 8
        if char.startswith("Shift") and with_control or char.startswith("Control") and with_shift \
                or char == "??" and with_control and with_shift:
                # simulate SHIFT+COMMODORE_KEY to flip the charset
                self.screen.shifted = not self.screen.shifted
                return

        if self.basic.running_program:
            # we're running a program, only the break key should do something!
            if char == '\x03' and with_control:  # ctrl+C
                self.runstop()
            elif char == '\x1b':    # esc
                self.runstop()
            else:
                self.basic.keybuffer.append((char, state, mousex, mousey))
            return

        if len(char) == 1:
            # if '1' <= char <= '8' and self.key_control_down:
            #     self.c64screen.text = ord(char)-1
            if char == '\r':    # RETURN key
                line = self.screen.current_line(2)
                self.screen.return_key()
                if not with_shift:
                    self.screen.cursor_enabled = False
                    self.execute_direct_line(line)
            elif char in ('\x08', '\x7f', 'Delete'):
                if with_shift:
                    self.screen.insert()
                else:
                    self.screen.backspace()
            elif char == '\x03' and with_control:  # ctrl+C
                self.runstop()
            elif char == '\x1b':    # esc
                self.runstop()
            else:
                self.screen.writestr(char)
            self.repaint()
        else:
            # some control character
            if char == "Up":
                self.screen.up()
                self.repaint()
            elif char == "Down":
                self.screen.down()
                self.repaint()
            elif char == "Left":
                self.screen.left()
                self.repaint()
            elif char == "Right":
                self.screen.right()
                self.repaint()
            elif char == 'Home':
                if with_shift:
                    self.screen.clearscreen()
                else:
                    self.screen.cursormove(0, 0)
                self.repaint()
            elif char in ('Insert', 'Help'):
                self.screen.insert()
                self.repaint()
            elif char == 'F7':      # directory shortcut key
                self.screen.writestr(self.basic.F7_dir_command + "\n")
                self.execute_direct_line(self.basic.F7_dir_command)
            elif char == 'F5':      # load file shortcut key
                if with_shift:
                    self.screen.writestr(self.basic.F6_load_command + "\n")
                    self.execute_direct_line(self.basic.F6_load_command)
                else:
                    self.screen.writestr(self.basic.F5_load_command)
                    line = self.screen.current_line(1)
                    self.screen.return_key()
                    self.execute_direct_line(line)
            elif char == "F3":      # run program shortcut key
                self.screen.writestr(self.basic.F3_run_command + "\n")
                self.execute_direct_line(self.basic.F3_run_command)
            elif char == "F1":      # list program shortcut key
                self.screen.writestr(self.basic.F1_list_command + "\n")
                self.execute_direct_line(self.basic.F1_list_command)
            elif char == "Prior":     # pageup = RESTORE (outside running program)
                if not self.basic.running_program:
                    self.screen.reset()
                    self.basic.write_prompt("\n")

    def execute_direct_line(self, line):
        try:
            line = line.strip()
            if line.startswith("gopy"):
                self.switch_interpreter("python")
                return
            elif line.startswith((">>> go64", "go64")):
                self.switch_interpreter("basic")
                return
            self.basic.execute_line(line)
        except ResetMachineException:
            self.reset_machine()
        finally:
            self.screen.cursor_enabled = True

    def switch_interpreter(self, interpreter):
        self.screen.reset()
        self.update()
        if self._cyclic_interpret_after is not None:
            self.after_cancel(self._cyclic_interpret_after)
        if interpreter == "basic":
            self.basic = BasicInterpreter(self.screen)
            self.basic_interpret_loop()
        elif interpreter == "python":
            self.basic = PythonInterpreter(self.screen)
        else:
            raise ValueError("invalid interpreter")

    def runstop(self):
        if self.basic.running_program:
            if self.basic.sleep_until:
                line = self.basic.program_lines[self.basic.next_run_line_idx - 1]
            else:
                line = self.basic.program_lines[self.basic.next_run_line_idx]
            try:
                self.basic.stop_run()
            except HandleBufferedKeysException:
                pass   # when breaking, no buffered keys will be processed
            self.screen.writestr("\nbreak in {:d}\nready.\n".format(line))
            self.screen.cursor_enabled = True

    def keyrelease(self, char, state, mousex, mousey):
        # print("keyrelease", repr(char), state, keycode)
        pass

    def create_bitmaps(self):
        os.makedirs(self.temp_graphics_folder, exist_ok=True)
        with open(self.temp_graphics_folder + "/readme.txt", "w") as f:
            f.write("this is a temporary folder to cache pyc64 files for tkinter graphics bitmaps.\n")
        # normal
        with Image.open(io.BytesIO(pkgutil.get_data(__name__, "charset/charset-normal.png"))) as source_chars:
            for i in range(256):
                filename = self.temp_graphics_folder + "/char-{:02x}.xbm".format(i)
                if not os.path.isfile(filename):
                    chars = source_chars.copy()
                    row, col = divmod(i, 40)
                    ci = chars.crop((col * 16, row * 16, col * 16 + 16, row * 16 + 16))
                    ci = ci.convert(mode="1", dither=None)
                    ci.save(filename, "xbm")
        # shifted
        with Image.open(io.BytesIO(pkgutil.get_data(__name__, "charset/charset-shifted.png"))) as source_chars:
            for i in range(256):
                filename = self.temp_graphics_folder + "/char-sh-{:02x}.xbm".format(i)
                if not os.path.isfile(filename):
                    chars = source_chars.copy()
                    row, col = divmod(i, 40)
                    ci = chars.crop((col * 16, row * 16, col * 16 + 16, row * 16 + 16))
                    ci = ci.convert(mode="1", dither=None)
                    ci.save(filename, "xbm")
        # 8 monochrome sprites (including their double-size variants)
        for i in range(8):
            with Image.new("1", (24, 21), color=1) as si:
                draw = ImageDraw.Draw(si)
                draw.text((8, 4), str(i))
                si = si.resize((48, 42), 0)
                si.save(self.temp_graphics_folder + "/sprite-{:d}.xbm".format(i), "xbm")
                dx = si.resize((96, 42), 0)
                dx.save(self.temp_graphics_folder + "/sprite-{:d}-2x.xbm".format(i), "xbm")
                dy = si.resize((48, 84), 0)
                dy.save(self.temp_graphics_folder + "/sprite-{:d}-2y.xbm".format(i), "xbm")
                dxy = si.resize((96, 84), 0)
                dxy.save(self.temp_graphics_folder + "/sprite-{:d}-2x-2y.xbm".format(i), "xbm")

    def repaint(self):
        # set bordercolor, done by setting the 4 border rectangles
        # (screen color done by setting the background color of all character bitmaps,
        #  this is a lot faster than using many transparent bitmaps!)
        bordercolor = self.tkcolor(self.screen.border)
        if self.canvas.itemcget(self.border1, "fill") != bordercolor:
            self.canvas.itemconfigure(self.border1, fill=bordercolor)
            self.canvas.itemconfigure(self.border2, fill=bordercolor)
            self.canvas.itemconfigure(self.border3, fill=bordercolor)
            self.canvas.itemconfigure(self.border4, fill=bordercolor)
        prefix = "char-sh" if self.screen.shifted else "char"
        if self.repaint_only_dirty:
            dirty = iter(self.screen.getdirty())
        else:
            chars, colors = self.screen.getscreencopy()
            dirty = enumerate(zip(chars, colors))
        screencolor = self.tkcolor(self.screen.screen)
        for index, (char, color) in dirty:
            forecol = self.tkcolor(color)
            bm = self.charbitmaps[index]
            bitmap = "@" + self.temp_graphics_folder + "/{:s}-{:02x}.xbm".format(prefix, char)
            self.canvas.itemconfigure(bm, foreground=forecol, background=screencolor, bitmap=bitmap)
        # sprite colors
        for snum, scol in enumerate(self.screen.getspritecolors()):
            spritecolor = self.tkcolor(scol)
            if self.canvas.itemcget(self.spritebitmaps[snum], "foreground") != spritecolor:
                self.canvas.itemconfigure(self.spritebitmaps[snum], foreground=spritecolor)
        # sprite positions
        for snum, spos in enumerate(self.screen.getspritepositions()):
            x, y = self.screencor_sprite(spos)
            self.canvas.coords(self.spritebitmaps[snum], x, y)
        # sprite double sizes
        for snum, (dx, dy) in enumerate(self.screen.getspritedoubles()):
            extension = "-2x" if dx else ""
            extension += "-2y" if dy else ""
            current_bm = self.canvas.itemcget(self.spritebitmaps[snum], "bitmap")
            if (extension and extension not in current_bm) or (not extension and ("-2x" in current_bm or "-2y" in current_bm)):
                bm = "@{:s}/sprite-{:d}{:s}.xbm".format(self.temp_graphics_folder, snum, extension)
                self.canvas.itemconfigure(self.spritebitmaps[snum], bitmap=bm)

    def screencor(self, cc):
        return 64 + cc[0] * 16, 64 + cc[1] * 16

    def screencor_sprite(self, cc):
        # sprite upper left = (24, 50) so subtract this from regular origin (64, 64)
        return 16 + cc[0] * 2, cc[1] * 2 - 36

    def tkcolor(self, color):
        return "#{:06x}".format(colorpalette[color % 16])

    def reset_machine(self):
        self.screen.reset()
        self.switch_interpreter("basic")
        self.update()

    def basic_interpret_loop(self):
        if not isinstance(self.basic, BasicInterpreter):
            return
        self.screen.cursor_enabled = not self.basic.running_program
        try:
            self.basic.interpret_program_step()
        except ResetMachineException:
            self.reset_machine()
        except HandleBufferedKeysException as kx:
            key_events = kx.args[0]
            for char, state, mousex, mousey in key_events:
                self.keypress(char, state, mousex, mousey)
        # Introduce an artificial delay here, to get at least *some* sense of the old times.
        # note: after_update makes it a lot faster, but is really slow on some systems
        # (windows) and it interferes with normal event handling (buttons etc, on osx)
        self._cyclic_interpret_after = self.after(1, self.basic_interpret_loop)


def start():
    ScreenAndMemory.test_screencode_mappings()
    emu = EmulatorWindow("Fast Commodore-64 'emulator' in pure Python!")
    emu.mainloop()


if __name__ == "__main__":
    start()