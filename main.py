#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Chord to MIDI Generator (v11.8 - UI Sorting and New 'blk' Chord)
- Reordered the Quality dropdown list for better usability.
- Added a new special chord quality: 'blk' (e.g., Cblk = A#aug/C).
- Implemented parsing and voicing logic for the new 'blk' chord.
"""
import sys
import re
import atexit
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import os
import platform
import inspect
import hashlib

import tkinter as tk
from tkinter import PhotoImage, filedialog, messagebox
import tkinter.ttk as ttk
import customtkinter as ctk
from mido import Message, MidiFile, MidiTrack, MetaMessage, bpm2tempo

_OPTIONMENU_PARAMS = set(inspect.signature(ctk.CTkOptionMenu.__init__).parameters)
_OPTIONMENU_SUPPORTS_FONT = 'font' in _OPTIONMENU_PARAMS
_OPTIONMENU_SUPPORTS_DROPDOWN_FONT = 'dropdown_font' in _OPTIONMENU_PARAMS

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

APP_TITLE = "Chord-to-MIDI-GENERATOR"
LOGFILE = "chord_to_midi.log"
CURRENT_VERSION = "1.2.2"

_SINGLE_INSTANCE_LOCK_FILE = None


def acquire_single_instance_lock(lock_path: str) -> bool:
    global _SINGLE_INSTANCE_LOCK_FILE
    try:
        lock_file = open(lock_path, "a+b")
    except OSError:
        return False

    try:
        if sys.platform == "win32":
            try:
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                lock_file.close()
                return False
        else:
            try:
                fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                lock_file.close()
                return False
    except Exception:
        lock_file.close()
        return False

    _SINGLE_INSTANCE_LOCK_FILE = lock_file
    return True


def release_single_instance_lock() -> None:
    global _SINGLE_INSTANCE_LOCK_FILE
    if not _SINGLE_INSTANCE_LOCK_FILE:
        return
    try:
        if sys.platform == "win32":
            try:
                _SINGLE_INSTANCE_LOCK_FILE.seek(0)
                msvcrt.locking(_SINGLE_INSTANCE_LOCK_FILE.fileno(), msvcrt.LK_UNLCK, 1)
            except OSError:
                pass
        else:
            try:
                fcntl.flock(_SINGLE_INSTANCE_LOCK_FILE, fcntl.LOCK_UN)
            except OSError:
                pass
    finally:
        try:
            _SINGLE_INSTANCE_LOCK_FILE.close()
        except OSError:
            pass
        _SINGLE_INSTANCE_LOCK_FILE = None


def notify_instance_already_running(message: str) -> None:
    try:
        if sys.platform == "win32":
            import ctypes
            MB_ICONWARNING = 0x00000030
            MB_OK = 0x00000000
            MB_TOPMOST = 0x00040000
            ctypes.windll.user32.MessageBoxW(None, message, APP_TITLE, MB_ICONWARNING | MB_OK | MB_TOPMOST)
        else:
            root = tk.Tk()
            root.withdraw()
            messagebox.showwarning(APP_TITLE, message, parent=root)
            root.destroy()
    except Exception:
        print(message)


atexit.register(release_single_instance_lock)

class ScrollableFrame(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.grid_rowconfigure(0, weight=1); self.grid_columnconfigure(0, weight=1)
        bg_color = ctk.ThemeManager.theme["CTkScrollableFrame"]["fg_color"]
        self.canvas = tk.Canvas(self, highlightthickness=0, bg=self._apply_appearance_mode(bg_color))
        self.vsb = ctk.CTkScrollbar(self, orientation="vertical", command=self.canvas.yview); self.canvas.configure(yscrollcommand=self.vsb.set)
        self.inner = ctk.CTkFrame(self, fg_color="transparent"); self.inner_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        # Bind mouse wheel events for scrolling.
        # We bind to the canvas widget, which is a standard tkinter widget.
        # Its bind_all method will correctly bind to the top-level window.
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel_event, add="+")
        self.canvas.bind_all("<Button-4>", self._on_mousewheel_event, add="+")
        self.canvas.bind_all("<Button-5>", self._on_mousewheel_event, add="+")

        self.canvas.grid(row=0, column=0, sticky="nsew"); self.vsb.grid(row=0, column=1, sticky="ns")
        self.inner.bind("<Configure>", self._on_inner_configure); self.canvas.bind("<Configure>", self._on_canvas_configure)
    def _on_inner_configure(self, event): self.canvas.configure(scrollregion=self.canvas.bbox("all"))
    def _on_canvas_configure(self, event): self.canvas.itemconfig(self.inner_id, width=event.width)
    def _on_mousewheel_event(self, event):
        x, y = self.winfo_pointerxy()
        target = self.winfo_containing(x, y)
        if target is None: return

        w = target
        while w is not None:
            if w == self:
                if sys.platform.startswith("linux"):
                    if event.num == 4: self.canvas.yview_scroll(-1, "units")
                    elif event.num == 5: self.canvas.yview_scroll(1, "units")
                elif sys.platform == "darwin":
                    # This revised logic provides a more consistent scrolling speed
                    # by scrolling a fixed number of units based on the direction
                    # of the scroll, avoiding issues with large event.delta values.
                    if event.delta > 0:
                        self.canvas.yview_scroll(-2, "units")
                    elif event.delta < 0:
                        self.canvas.yview_scroll(2, "units")
                else: # Windows
                    self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
                return
            try: w = w.master
            except Exception: break


class UpdateProgressWindow:
    def __init__(self, title="업데이트 진행 중"):
        self._created_root = False
        parent = tk._default_root
        if parent is None:
            self.window = tk.Tk()
            self._created_root = True
        else:
            self.window = tk.Toplevel(parent)
            self.window.transient(parent)

        self.window.title(title)
        self.window.geometry("360x170")
        self.window.resizable(False, False)
        self.window.attributes("-topmost", True)
        self.window.protocol("WM_DELETE_WINDOW", lambda: None)

        self.status_var = tk.StringVar(master=self.window, value="준비 중...")
        status_label = tk.Label(self.window, textvariable=self.status_var, font=("Helvetica", 12))
        status_label.pack(pady=(20, 10))

        self.progress = ttk.Progressbar(self.window, orient="horizontal", mode="determinate", length=280)
        self.progress.pack(pady=5)
        self.progress['maximum'] = 100
        self._progress_mode = "determinate"

        self.percent_var = tk.StringVar(master=self.window, value="0%")
        percent_label = tk.Label(self.window, textvariable=self.percent_var, font=("Helvetica", 10))
        percent_label.pack(pady=(0, 10))

        info_label = tk.Label(self.window, text="창을 닫지 마세요", font=("Helvetica", 9))
        info_label.pack()

        self.window.update_idletasks()

    def _ensure_mode(self, mode: str):
        if self._progress_mode == mode:
            return
        if self._progress_mode == "indeterminate":
            self.progress.stop()
        self.progress.config(mode=mode)
        if mode == "indeterminate":
            self.progress.start(12)
        self._progress_mode = mode

    def update_status(self, text: str, percent: Optional[float] = None):
        self.status_var.set(text)
        if percent is None:
            self._ensure_mode("indeterminate")
            self.percent_var.set("")
        else:
            self._ensure_mode("determinate")
            clamped = max(0.0, min(100.0, percent))
            self.progress['value'] = clamped
            self.percent_var.set(f"{clamped:.0f}%")
        self.window.update_idletasks()

    def close(self):
        if self._progress_mode == "indeterminate":
            self.progress.stop()
        if self.window:
            self.window.destroy()


def format_bytes(num: int) -> str:
    value = float(num)
    units = ["B", "KB", "MB", "GB", "TB"]
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{num} B"

class App(ctk.CTk):
    BASE_OCTAVE = 48
    NOTE_NAMES_SHARP = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    NOTE_NAMES_FLAT  = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B']
    KEYS = ['C', 'C#', 'Db', 'D', 'Eb', 'E', 'F', 'F#', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B', 'Cb']
    KEY_PREFERS_SHARPS = {'C':True,'G':True,'D':True,'A':True,'E':True,'B':True,'F#':True,'C#':True, 'F':False,'Bb':False,'Eb':False,'Ab':False,'Db':False,'Gb':False,'Cb':False}
    MAJOR_DEGREE_TO_SEMITONES = {'I':0, 'II':2, 'III':4, 'IV':5, 'V':7, 'VI':9, 'VII':11}
    TENSIONS_LIST = ['b9', '9', '#9', '11', '#11', 'b13', '13']
    # [REQUEST] Reorder list and add 'blk'
    QUALITY_SYMBOLS = ["Major", "Minor", "7", "M7", "m7", "7b5", "M7b5", "m7b5", "dim", "dim7", "aug", "blk", "sus2", "sus4", "omit3", "omit5"]
    ROMAN_DEGREES_BUILDER = ['I', 'bII', 'II', 'bIII', 'III', 'IV', '#IV', 'V', 'bVI', 'VI', 'bVII', 'VII']
    PART_COLORS = ['#3a6ea5', '#ff885b', '#57a773', '#b86fc6', '#f2c14e', '#e63946', '#6d597a', '#277da1', '#bc6c25', '#118ab2']
    PART_GROUP_BG = ('#eef3fa', '#1a2330')

    @staticmethod
    def roman_degrees_for_key(key: str) -> List[str]:
        prefer_sharp = App.prefers_sharps(key)
        base = {0:'I', 2:'II', 4:'III', 5:'IV', 7:'V', 9:'VI', 11:'VII'}
        acc = {1:('#I','bII'), 3:('#II','bIII'), 6:('#IV','bV'), 8:('#V','bVI'), 10:('#VI','bVII')}
        out = []
        for sem in [0,1,2,3,4,5,6,7,8,9,10,11]:
            if sem in base: out.append(base[sem])
            else:
                sharp_name, flat_name = acc[sem]
                out.append(sharp_name if prefer_sharp else flat_name)
        return out

    @staticmethod
    def color_for_part(part_name: str) -> str:
        if not part_name:
            return 'transparent'
        digest = hashlib.md5(part_name.lower().encode('utf-8')).hexdigest()
        index = int(digest, 16) % len(App.PART_COLORS)
        return App.PART_COLORS[index]

    ROMAN_PATTERN = r'(?:VII|VI|V|IV|III|II|I)'
    ROMAN_RE = re.compile(fr'(?i)^([b#]?)({ROMAN_PATTERN})$')
    
    @staticmethod
    def resource_path(relative_path):
        try: base_path = sys._MEIPASS
        except Exception: base_path = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(base_path, relative_path)
    
    @dataclass
    class ParsedChord:
        root: str
        quality: str
        tensions: List[str] = field(default_factory=list)
        paren_contents: List[str] = field(default_factory=list)
        bass_note: Optional[str] = None
        omissions: List[int] = field(default_factory=list)
        is_roman: bool = False
        roman_symbol: Optional[str] = None
        seventh: Optional[str] = None
        alterations: List[str] = field(default_factory=list)

    @staticmethod
    def prefers_sharps(key: str) -> bool: return App.KEY_PREFERS_SHARPS.get(key, True)
    
    @staticmethod
    def name_to_pc(name: str) -> int:
        tbl = {'C':0,'B#':0,'C#':1,'Db':1,'D':2,'D#':3,'Eb':3,'E':4,'Fb':4,'F':5,'E#':5,'F#':6,'Gb':6,'G':7,'G#':8,'Ab':8,'A':9,'A#':10,'Bb':10,'B':11,'Cb':11}
        n = name.strip()
        if len(n)>1 and n[1] in ('b','#'): n = n[0].upper() + n[1:]
        else: n = n[0].upper() + n[1:].lower()
        if n not in tbl: raise ValueError(f"Unknown note name: {n}")
        return tbl[n]

    @staticmethod
    def pc_to_name(pc: int, use_sharps: bool) -> str: return App.NOTE_NAMES_SHARP[pc%12] if use_sharps else App.NOTE_NAMES_FLAT[pc%12]
    
    @staticmethod
    def parse_tensions(text: str) -> List[str]:
        if not text: return []
        inner = text.strip()
        if inner.startswith('(') and inner.endswith(')'): inner = inner[1:-1]
        if not inner: return []
        parts = [p.strip() for p in inner.split(',') if p.strip()]
        norm = [p.replace('+', '#').replace('-', 'b') for p in parts if re.fullmatch(r'(?:b|#)?(?:5|9|11|13)', p.replace('+', '#').replace('-', 'b'))]
        seen, out = set(), []
        for t in norm:
            core_num = ''.join(filter(str.isdigit, t))
            if core_num not in seen: out.append(t); seen.add(core_num)
        return out
        
    @staticmethod
    def roman_to_pc_offset(key_root: str, roman: str) -> int:
        m = App.ROMAN_RE.fullmatch(roman)
        if not m: raise ValueError(f"Invalid roman: {roman}")
        acc, deg = m.groups(); semis = App.MAJOR_DEGREE_TO_SEMITONES[deg.upper()]
        if acc.lower() == 'b': semis -= 1
        elif acc == '#': semis += 1
        return (App.name_to_pc(key_root) + semis) % 12

    @staticmethod
    def parse_chord_symbol(text: str, key: str) -> 'App.ParsedChord':
        s = (text or '').strip()
        if not s:
            return App.ParsedChord(root='C', quality='Major')

        replacements = {
            '♭': 'b',
            '♯': '#',
            '♮': '',
            '𝄪': '##',
            '𝄫': 'bb',
            '＃': '#',
            'ｂ': 'b',
        }
        for src, dst in replacements.items():
            if src in s:
                s = s.replace(src, dst)

        # 'blk' 품질을 먼저 파싱하여 근음과의 모호함 제거
        is_blk = 'blk' in s.lower()
        if is_blk:
            s = re.sub('blk', '', s, flags=re.IGNORECASE).strip()
        
        bass_note = None
        if '/' in s:
            parts = s.split('/', 1); s = parts[0].strip()
            try: bass_note = App.pc_to_name(App.name_to_pc(parts[1].strip()), App.prefers_sharps(key))
            except ValueError: bass_note = None

        omissions = []
        if 'omit3' in s: omissions.append(3); s = s.replace('omit3', '').strip()
        if 'omit5' in s: omissions.append(5); s = s.replace('omit5', '').strip()

        paren_contents = []
        tens_match = re.search(r'\(.*\)', s)
        if tens_match:
            tensions_str = tens_match.group(0)
            paren_contents = App.parse_tensions(tensions_str)
            s = s.replace(tensions_str, '').strip()
            if not s and not paren_contents:
                inner = tensions_str[1:-1].strip()
                if inner:
                    s = inner

        s = s.replace('maj7', 'M7').replace('Maj7','M7').replace('min','m').replace('ø', 'm7b5').replace('°', 'dim')

        # Handle +/- alterations before '-' is treated as minor.
        # This correctly handles C7-5 (C7b5) vs C-7 (Cm7).
        s = s.replace('-5', 'b5').replace('+5', '#5')
        s = s.replace('-9', 'b9').replace('+9', '#9')
        s = s.replace('+11', '#11')
        s = s.replace('-13', 'b13')

        # Now, handle standalone '-' as minor
        s = s.replace('-', 'm')

        m_roman = re.match(fr'(?i)^([b#]?{App.ROMAN_PATTERN})', s)
        if m_roman:
            head = m_roman.group(1); is_roman_flag = True; rest = s[len(head):].strip()
            root = App.pc_to_name(App.roman_to_pc_offset(key, head), App.prefers_sharps(key))
        else:
            m_alpha = re.match(r'(?i)^([A-G][#b]?)', s)
            if m_alpha:
                head = m_alpha.group(1); is_roman_flag = False; rest = s[len(head):].strip()
                root = head[0].upper() + head[1:]
            else:
                raise ValueError(f"Unrecognized chord symbol '{text}'")

        quality, seventh, tensions, alterations = 'Major', None, [], []
        rest_mut = rest

        if '13' in rest_mut: tensions.append('13'); rest_mut = rest_mut.replace('13', '')
        if '11' in rest_mut: tensions.append('11'); rest_mut = rest_mut.replace('11', '')
        if '9' in rest_mut: tensions.append('9'); rest_mut = rest_mut.replace('9', '')
        if '6' in rest_mut: tensions.append('6'); rest_mut = rest_mut.replace('6', '')
        
        sev_m = re.search(r'M7|m7|7|dim7', rest_mut)
        if sev_m:
            sev_str = sev_m.group(0)
            seventh = 'm7' if sev_str == '7' else sev_str
            rest_mut = rest_mut.replace(sev_str, '')
            if sev_str == 'm7': quality = 'Minor'
            elif sev_str == 'dim7': quality = 'dim'
        elif tensions or paren_contents:
            # Don't add a 7th automatically if the only tension is '6'
            non_six_tensions = [t for t in tensions if t != '6']
            if non_six_tensions or paren_contents:
                is_minor_in_parens = any('m' in p for p in paren_contents)
                if not is_minor_in_parens:
                    seventh = 'm7'

        if is_blk:
            quality = 'blk'
        elif 'sus4' in rest_mut: quality = 'sus4'; rest_mut = rest_mut.replace('sus4', '')
        elif 'sus2' in rest_mut: quality = 'sus2'; rest_mut = rest_mut.replace('sus2', '')
        elif 'aug' in rest_mut or '+' in rest_mut: quality = 'aug'; rest_mut = rest_mut.replace('aug','').replace('+','')
        elif 'dim' in rest_mut: quality = 'dim'; rest_mut = rest_mut.replace('dim','')
        elif 'm' in rest_mut: quality = 'Minor'; rest_mut = rest_mut.replace('m','')
        
        if is_roman_flag and head.islower() and not rest:
             if head.upper() in ['II','III','VI']: quality = 'Minor'
             elif head.upper() == 'VII': quality = 'dim'
        
        if 'b5' in rest_mut: alterations.append('b5')
        if '#5' in rest_mut: alterations.append('#5')
        
        if 'm7b5' in rest: quality, seventh, alterations = 'dim', 'm7', []
        
        return App.ParsedChord(root=root, quality=quality, tensions=tensions, paren_contents=paren_contents,
                               bass_note=bass_note, omissions=omissions, is_roman=is_roman_flag,
                               roman_symbol=head, seventh=seventh, alterations=alterations)

    @staticmethod
    def build_string_from_parsed(p: 'App.ParsedChord', is_roman: bool, key: str) -> str:
        if is_roman:
            if p.is_roman and p.roman_symbol is not None: base = p.roman_symbol
            else:
                key_pc, root_pc = App.name_to_pc(key), App.name_to_pc(p.root)
                diff = (root_pc - key_pc + 12) % 12
                sem_to_deg = {sem: deg for deg, sem in App.MAJOR_DEGREE_TO_SEMITONES.items()}
                base = None
                if diff in sem_to_deg: base = sem_to_deg[diff]
                else:
                    use_sharps = App.prefers_sharps(key)
                    raised_pc = (diff - 1 + 12) % 12; flatted_pc = (diff + 1) % 12
                    if use_sharps and raised_pc in sem_to_deg: base = '#' + sem_to_deg[raised_pc]
                    elif not use_sharps and flatted_pc in sem_to_deg: base = 'b' + sem_to_deg[flatted_pc]
                    else: base = 'b' + sem_to_deg.get(flatted_pc, 'I')
                base = base or 'I'
        else: base = p.root

        qual_str = ''
        if p.quality == 'Minor': qual_str = 'm'
        elif p.quality == 'dim' and not (p.seventh == 'm7' or p.seventh == 'dim7'): qual_str = 'dim'
        elif p.quality == 'aug': qual_str = 'aug'
        elif p.quality == 'blk': qual_str = 'blk'
        elif p.quality == 'sus2': qual_str = 'sus2'
        elif p.quality == 'sus4': qual_str = 'sus4'

        has_6 = '6' in p.tensions
        other_tensions = [t for t in p.tensions if t != '6']

        highest_tension_num = 0
        if other_tensions:
            highest_tension_num = max([int(re.sub(r'[^0-9]','',t)) for t in other_tensions])

        six_part = '6' if has_6 else ''
        num_part = ''
        sev_prefix = ''
        if highest_tension_num > 7:
            num_part = str(highest_tension_num)
            if p.seventh == 'M7': sev_prefix = 'M'
        elif p.seventh:
            num_part = '7'
            if p.seventh == 'M7': sev_prefix = 'M'
            elif p.seventh == 'dim7': qual_str, num_part = '', 'dim7'

        if p.quality == 'dim' and p.seventh == 'm7':
            qual_str, sev_prefix, num_part, alt_str, six_part = '', 'm', '7b5', '', ''
        else:
            alt_str = ''.join(p.alterations)

        paren_str = f"({','.join(p.paren_contents)})" if p.paren_contents else ''
        om_str = ''.join([f"omit{o}" for o in p.omissions])
        bass_str = f"/{p.bass_note}" if p.bass_note and p.bass_note != p.root else ""

        return f"{base}{qual_str}{six_part}{sev_prefix}{num_part}{alt_str}{om_str}{paren_str}{bass_str}"

    @staticmethod
    def build_voicing(parsed: 'App.ParsedChord', omit5_on_conflict: bool, omit_duplicated_bass: bool) -> List[int]:
        root_pc = App.name_to_pc(parsed.root)
        intervals = []
        
        if parsed.quality == 'blk':
            # blk is special: Root of aug triad is M2 below the stated root/bass
            # Intervals are relative to the stated root, which is the bass
            # e.g for Cblk, root is C, notes are A#aug/C -> C bass, A#-D-F# chord
            # Intervals from C(0) are D(2), F#(6), A#(10)
            intervals.extend([2, 6, 10]) # M2, A4, m7 from the bass
        else:
            all_tensions = parsed.tensions + parsed.paren_contents

            if parsed.quality == 'Minor': intervals.extend([0, 3, 7])
            elif parsed.quality == 'dim': intervals.extend([0, 3, 6])
            elif parsed.quality == 'aug': intervals.extend([0, 4, 8])
            else: intervals.extend([0, 4, 7]) # Major default

            if parsed.quality == 'sus2': intervals = [i for i in intervals if i not in [3,4]] + [2]
            if parsed.quality == 'sus4': intervals = [i for i in intervals if i not in [3,4]] + [5]

            if parsed.seventh == 'm7': intervals.append(10)
            elif parsed.seventh == 'M7': intervals.append(11)
            elif parsed.seventh == 'dim7': intervals.append(9)

            if 'b5' in parsed.alterations: intervals = [i for i in intervals if i not in [7,8]] + [6]
            if '#5' in parsed.alterations: intervals = [i for i in intervals if i not in [6,7]] + [8]

            if 3 in parsed.omissions: intervals = [i for i in intervals if i not in [2,3,4,5]]
            if 5 in parsed.omissions: intervals = [i for i in intervals if i not in [6,7,8]]

            tension_map = {'6': 9, '9':14, 'b9':13, '#9':15, '11':17, '#11':18, '13':21, 'b13':20}
            if omit5_on_conflict and any(t in all_tensions for t in ['#11','b13']):
                intervals = [iv for iv in intervals if iv % 12 != 7]
            for t in all_tensions:
                if t in tension_map: intervals.append(tension_map[t])
        
        intervals = sorted(list(set(intervals)))

        bass_pc = App.name_to_pc(parsed.bass_note) if parsed.bass_note else root_pc
        bass_midi_note = (App.BASE_OCTAVE - 12) + bass_pc
        
        # For 'blk' chords, the root of the chord part is different from the bass
        chord_root_pc = (root_pc - 2 + 12) % 12 if parsed.quality == 'blk' else root_pc
        
        final_chord_notes = []; root_note_in_voicing = App.BASE_OCTAVE + chord_root_pc
        
        if 0 in intervals and parsed.quality != 'blk': final_chord_notes.append(root_note_in_voicing)
        
        sorted_intervals = sorted([iv for iv in intervals if iv != 0 or parsed.quality == 'blk'])
        
        last_note = root_note_in_voicing if final_chord_notes else App.BASE_OCTAVE + bass_pc
        
        for iv in sorted_intervals:
            pitch_iv = iv; is_13th_tension = False
            if iv in [13, 14, 15]: pitch_iv -= 12
            elif iv in [17, 18]: pitch_iv -= 12
            elif iv in [20, 21]: pitch_iv -= 12; is_13th_tension = True

            note_pc = (root_pc + pitch_iv) % 12
            
            candidate = (last_note // 12) * 12 + note_pc
            if candidate <= last_note: candidate += 12
            
            if is_13th_tension and (candidate >= root_note_in_voicing + 20): candidate -= 12
            
            final_chord_notes.append(candidate)
            final_chord_notes.sort(); last_note = final_chord_notes[-1]
            
        if omit_duplicated_bass:
            final_chord_notes = [note for note in final_chord_notes if note % 12 != bass_pc]
        
        final_notes = [bass_midi_note] + final_chord_notes
        return sorted(list(set(final_notes)))

    @staticmethod
    def split_measure_text(text: str) -> List[str]:
        return [part for part in text.split(' ') if part]

    @staticmethod
    def duration_ticks_for_n(n: int, tpb: int) -> List[int]:
        if n == 3:
            return [2 * tpb, tpb, tpb]
        base_dur = (4 * tpb) // n
        rem = (4 * tpb) % n
        durations = [base_dur + 1 if i < rem else base_dur for i in range(n)]
        return durations

    def __init__(self, splash_root):
        super().__init__()
        self.splash_root = splash_root
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme(App.resource_path("pro_theme.json"))
        self.i18n = {
            "ko": {
                "title": "Chord to MIDI",
                "key": "키",
                "part": "파트",
                "inherit_key": "-",
                "alphabet": "알파벳",
                "degree": "도수",
                "omit5": "5음 생략",
                "omit_bass": "베이스 중복음 생략",
                "measures": "마디",
                "generate_midi": "MIDI 생성",
                "clear_all": "모두 지우기",
                "load_chart": "불러오기",
                "save_chart": "저장하기",
                "builder_title": "코드 빌더",
                "root": "근음",
                "quality": "종류",
                "tensions": "텐션",
                "reset_tensions": "텐션 초기화",
                "build_insert": "코드 만들고 넣기",
                "instructions_text": "입력한 코드를 MIDI로 변환해주는 도구입니다.\n\n"
                     "## 기본 사용법\n"
                     "• 코드 구분은 공백만 사용됩니다. (예: C G/B Am7 F)\n"
                     "• 슬래시(/)는 베이스음을 지정합니다. (예: C/E는 C코드, 베이스 E)\n"
                     "• omit3, omit5로 3음, 5음을 생략할 수 있습니다. (예: C7omit3)\n"
                     "• 모든 코드는 한 옥타브 낮은 베이스음과 함께 연주됩니다.\n"
                     "• 코드 빌더는 선택한 마디 칸에 코드를 생성하는 도구입니다.\n\n"
                     "------------------------------------\n"
                     "## 악보 차트 파일(.txt) 규칙\n"
                     "텍스트 파일로 저장된 악보를 '불러오기' 기능으로 가져올 수 있습니다.\n\n"
                     "• `[파트 이름]` : 대괄호`[]`를 사용하여 Intro, Verse 등 파트를 지정합니다.\n"
                     "• `(Key:키)` : 소괄호`()`와 `Key:`를 조합하여 해당 파트의 키를 지정합니다.\n"
                     "• `|` (수직선) : 마디를 구분하는 기호입니다. 한 줄은 보통 4마디를 의미합니다.\n"
                     "• `%` (퍼센트) : 이전 마디의 코드를 그대로 반복하여 연주합니다.\n"
                     "• `공백` : 한 마디 안에 여러 코드를 입력할 경우 공백으로 구분합니다.\n\n"
                     "### 예시 코드:\n"
                     "[intro] (Key:C)\n"
                     "| FM7    | G7    | Em7    | Am7   |\n"
                     "| FM7    | G7    | Am7    | %     |\n\n"
                     "[A] (Key:Eb)\n"
                     "| Eb     | %          | AbM7   | Abm7  |\n"
                     "| Eb     | Eb Eb/Ab   | AbM7   | Abm7  |",
                "clear_confirm_title": "확인",
                "clear_confirm_message": "모든 마디에 입력된 코드를 정말로 지우시겠습니까?"
            },
            "en": {
                "title": "Chord to MIDI",
                "key": "Key",
                "part": "Part",
                "inherit_key": "-",
                "alphabet": "Alphabet",
                "degree": "Degree",
                "omit5": "Omit 5th",
                "omit_bass": "Omit Dupe Bass",
                "measures": "Measures",
                "generate_midi": "Generate MIDI",
                "clear_all": "Clear All",
                "load_chart": "Load Chart",
                "save_chart": "Save Chart",
                "builder_title": "Chord Builder",
                "root": "Root",
                "quality": "Quality",
                "tensions": "Tensions",
                "reset_tensions": "Reset Tensions",
                "build_insert": "Build & Insert Chord",
                "instructions_text": "This tool converts entered chords into MIDI notes.\n\n"
                     "## Basic Usage\n"
                     "• Use spaces to separate chords (e.g., C G/B Am7 F).\n"
                     "• Use a slash (/) to specify a bass note (e.g., C/E means a C chord with an E bass).\n"
                     "• Use omit3, omit5 to omit the 3rd or 5th (e.g., C7omit3).\n"
                     "• All chords are played with a bass note one octave lower.\n"
                     "• The Chord Builder helps you create and insert chords into the selected measure.\n\n"
                     "------------------------------------\n"
                     "## Chart File Rules (.txt)\n"
                     "You can load a chart saved as a text file using the 'Load Chart' feature.\n\n"
                     "• `[Part Name]`: Use square brackets `[]` to define part names like 'Intro' or 'Verse'.\n"
                     "• `(Key:Key)`: Use parentheses `()` with `Key:` to set the key signature for the part.\n"
                     "• `|` (Vertical Bar): Use the vertical bar to separate measures. A line typically represents four measures.\n"
                     "• `%` (Percent Sign): Repeats the chord(s) from the preceding measure.\n"
                     "• `Space`: Use spaces to separate multiple chords within a single measure.\n\n"
                     "### Example Code:\n"
                     "[intro] (Key:C)\n"
                     "| FM7    | G7    | Em7    | Am7   |\n"
                     "| FM7    | G7    | Am7    | %     |\n\n"
                     "[A] (Key:Eb)\n"
                     "| Eb     | %          | AbM7   | Abm7  |\n"

                     "| Eb     | Eb Eb/Ab   | AbM7   | Abm7  |",
                "clear_confirm_title": "Confirmation",
                "clear_confirm_message": "Are you sure you want to clear all chords from all measures?"
            }
        }
        self.lang_code = "ko"
        self.geometry("1200x800"); self.minsize(1080, 720)
        font_family = "NanumGothic" if platform.system() == "Windows" else "Segoe UI"
        self.font_main = ctk.CTkFont(family=font_family, size=14)
        self.font_measure_entry = ctk.CTkFont(family=font_family, size=13)
        self.font_small = ctk.CTkFont(family=font_family, size=12)
        self.font_bold = ctk.CTkFont(family=font_family, size=14, weight="bold")
        self.font_small_bold = ctk.CTkFont(family=font_family, size=12, weight="bold")
        self.font_large_bold = ctk.CTkFont(family=font_family, size=18, weight="bold")
        self.font_part_header = ctk.CTkFont(family=font_family, size=16, weight="bold")
        self.font_measure = ctk.CTkFont(family="Menlo", size=12)
        self._suppress, self._building, self.last_focused_entry = True, False, None
        self._pending_part_box_update = None

        self.grid_columnconfigure(0, weight=1); self.grid_columnconfigure(1, minsize=320, weight=0); self.grid_rowconfigure(2, weight=1)

        self.settings_top = ctk.CTkFrame(self, fg_color="transparent")
        self.settings_top.grid(row=0, column=0, columnspan=2, padx=10, pady=(10,4), sticky="ew")
        self.settings_bottom = ctk.CTkFrame(self, fg_color="transparent")
        self.settings_bottom.grid(row=1, column=0, columnspan=2, padx=10, pady=(0,6), sticky="ew")

        self.lang_var = tk.StringVar(master=self, value="한국어")
        self.lang_toggle = ctk.CTkSegmentedButton(self.settings_top, values=["한국어", "English"], variable=self.lang_var, command=self._update_language)
        self.lang_toggle.pack(side="left", padx=(0,6))
        self.inherit_key_label = self.i18n[self.lang_code]["inherit_key"]
        self.mode_var = tk.StringVar(master=self, value=self.i18n[self.lang_code]["alphabet"])
        self.mode_btn = ctk.CTkSegmentedButton(self.settings_top, variable=self.mode_var, command=self._on_mode_changed)
        self.mode_btn.pack(side="left", padx=(0,10))

        self.omit5_var = tk.BooleanVar(master=self, value=True)
        self.omit5_chk = ctk.CTkCheckBox(self.settings_top, variable=self.omit5_var, font=self.font_main)
        self.omit5_chk.pack(side="left", padx=(0,12))

        self.omit_bass_var = tk.BooleanVar(master=self, value=False)
        self.omit_bass_chk = ctk.CTkCheckBox(self.settings_top, variable=self.omit_bass_var, font=self.font_main)
        self.omit_bass_chk.pack(side="left", padx=(0,12))

        action_buttons_group = ctk.CTkFrame(self.settings_bottom, fg_color="transparent")
        action_buttons_group.pack(side="left")
        button_pad = (0, 6)
        self.load_chart_btn = ctk.CTkButton(action_buttons_group, font=self.font_main, command=self._load_chart_from_file, fg_color="transparent", border_width=1)
        self.load_chart_btn.pack(side="left", padx=button_pad)
        self.save_chart_btn = ctk.CTkButton(action_buttons_group, font=self.font_main, command=self._save_chart_to_file, fg_color="transparent", border_width=1)
        self.save_chart_btn.pack(side="left", padx=button_pad)
        self.clear_all_btn = ctk.CTkButton(action_buttons_group, font=self.font_main, command=self._clear_all_chords, fg_color="transparent", border_width=1)
        self.clear_all_btn.pack(side="left", padx=button_pad)
        self.gen_btn = ctk.CTkButton(action_buttons_group, font=self.font_bold, command=self._on_generate_midi)
        self.gen_btn.pack(side="left", padx=button_pad)

        self.main_area = ctk.CTkFrame(self, fg_color="transparent"); self.main_area.grid(row=2, column=0, padx=10, pady=5, sticky="nsew")
        self.main_area.grid_rowconfigure(0, weight=1); self.main_area.grid_columnconfigure(0, weight=1)
        self.scroll = ScrollableFrame(self.main_area); self.scroll.grid(row=0, column=0, sticky="nsew")
        self.measures_frame = self.scroll.inner
        self.measures_frame.grid_columnconfigure(0, weight=1) # This frame will hold part frames

        self.parts_data: List[Dict[str, Any]] = []
        self.measure_entries: List[ctk.CTkEntry] = []
        self.entry_part_map: Dict[ctk.CTkEntry, int] = {}
        self.entry_global_idx_map: Dict[ctk.CTkEntry, int] = {}
        self.part_widgets: List[Dict[str, Any]] = []
        self.add_part_btn: Optional[ctk.CTkButton] = None

        self.builder_frame = ctk.CTkFrame(self); self.builder_frame.grid(row=2, column=1, padx=(0,10), pady=5, sticky="ns")
        self.builder_frame.grid_columnconfigure(0, weight=1)
        self.builder_title_label = ctk.CTkLabel(self.builder_frame, font=self.font_large_bold); self.builder_title_label.grid(row=0, column=0, columnspan=4, padx=15, pady=(15,10), sticky="w")
        
        ctk.CTkFrame(self.builder_frame, height=1, fg_color=ctk.ThemeManager.theme["CTkFrame"]["border_color"]).grid(row=1, column=0, padx=15, pady=5, sticky="ew")
        self.root_label = ctk.CTkLabel(self.builder_frame, font=self.font_bold); self.root_label.grid(row=2, column=0, columnspan=4, padx=15, pady=(10,2), sticky="w")
        self.builder_root_var = tk.StringVar(master=self, value="C")
        builder_root_kwargs = {
            'values': App.NOTE_NAMES_SHARP,
            'variable': self.builder_root_var,
        }
        if _OPTIONMENU_SUPPORTS_FONT:
            builder_root_kwargs['font'] = self.font_main
        if _OPTIONMENU_SUPPORTS_DROPDOWN_FONT:
            builder_root_kwargs['dropdown_font'] = self.font_main
        self.builder_root_menu = ctk.CTkOptionMenu(self.builder_frame, **builder_root_kwargs)
        self.builder_root_menu.grid(row=3, column=0, columnspan=4, padx=15, pady=0, sticky="ew")
        
        self.quality_label = ctk.CTkLabel(self.builder_frame, font=self.font_bold); self.quality_label.grid(row=4, column=0, columnspan=4, padx=15, pady=(10,2), sticky="w")
        self.builder_quality_var = tk.StringVar(master=self, value="Major")
        builder_quality_kwargs = {
            'values': App.QUALITY_SYMBOLS,
            'variable': self.builder_quality_var,
        }
        if _OPTIONMENU_SUPPORTS_FONT:
            builder_quality_kwargs['font'] = self.font_main
        if _OPTIONMENU_SUPPORTS_DROPDOWN_FONT:
            builder_quality_kwargs['dropdown_font'] = self.font_main
        self.builder_quality_menu = ctk.CTkOptionMenu(self.builder_frame, **builder_quality_kwargs)
        self.builder_quality_menu.grid(row=5, column=0, columnspan=4, padx=15, pady=0, sticky="ew")
        
        ctk.CTkFrame(self.builder_frame, height=1, fg_color=ctk.ThemeManager.theme["CTkFrame"]["border_color"]).grid(row=6, column=0, padx=15, pady=10, sticky="ew")
        
        self.tensions_label = ctk.CTkLabel(self.builder_frame, font=self.font_bold); self.tensions_label.grid(row=7, column=0, columnspan=4, padx=15, pady=(5,5), sticky="w")
        self.tension_button_frame = ctk.CTkFrame(self.builder_frame, fg_color="transparent"); self.tension_button_frame.grid(row=8, column=0, columnspan=4, padx=15, pady=0, sticky="ew")
        self.tension_vars = {}
        for i, tension in enumerate(App.TENSIONS_LIST):
            var = tk.BooleanVar(master=self, value=False); self.tension_vars[tension] = var
            chk = ctk.CTkCheckBox(self.tension_button_frame, text=tension, variable=var, font=self.font_main); chk.grid(row=i//4, column=i%4, padx=2, pady=2, sticky="w")
        
        self.reset_tensions_btn = ctk.CTkButton(self.builder_frame, font=self.font_main, command=self._reset_tensions, fg_color="transparent", border_width=1); self.reset_tensions_btn.grid(row=9, column=0, columnspan=4, padx=15, pady=(10,5), sticky="ew")
        self.insert_btn = ctk.CTkButton(self.builder_frame, font=self.font_bold, command=self._on_build_and_insert); self.insert_btn.grid(row=10, column=0, columnspan=4, padx=15, pady=5, sticky="ew")
        
        self.bottom_tabs = ctk.CTkTabview(self, height=140); self.bottom_tabs.grid(row=3, column=0, columnspan=2, padx=10, pady=(5,10), sticky="ew")
        self.bottom_tabs.add("Instructions"); self.bottom_tabs.add("Log")
        self.instructions = ctk.CTkTextbox(self.bottom_tabs.tab("Instructions"), font=self.font_main, wrap="word"); self.instructions.pack(expand=True, fill="both", padx=5, pady=5)
        self.log = ctk.CTkTextbox(self.bottom_tabs.tab("Log"), font=self.font_measure, wrap="none"); self.log.pack(expand=True, fill="both", padx=5, pady=5)
        
        self.context_menu = self._create_context_menu()

        self.version_label = ctk.CTkLabel(self, text=f"v{CURRENT_VERSION}", font=ctk.CTkFont(size=12), text_color="gray50")
        self.version_label.grid(row=4, column=1, padx=10, pady=(0, 5), sticky="se")
        self.grid_rowconfigure(4, weight=0)

        def on_save_midi(event=None): self._on_generate_midi()

        self.protocol("WM_DELETE_WINDOW", self._on_closing)
        self._update_language(); self._suppress = False; self.after(50, self._initialize_chart); self._log("App started.")
        self.after(100, self.splash_root.withdraw)
        if sys.platform == "darwin":
            # macOS에서는 네이티브 메뉴바와 직접 바인딩을 함께 사용해 한글 입력기 호환성을 높입니다.
            menubar = tk.Menu(self)
            self.config(menu=menubar)

            # File 메뉴
            file_menu = tk.Menu(menubar, name='file')
            menubar.add_cascade(label='File', menu=file_menu)
            file_menu.add_command(label='Generate MIDI', accelerator='Cmd+S', command=on_save_midi)

            # Edit 메뉴
            edit_menu = tk.Menu(menubar, name='edit')
            menubar.add_cascade(label='Edit', menu=edit_menu)
            edit_menu.add_command(label='Cut', accelerator='Cmd+X', command=lambda: self.focus_get().event_generate('<<Cut>>'))
            edit_menu.add_command(label='Copy', accelerator='Cmd+C', command=lambda: self.focus_get().event_generate('<<Copy>>'))
            edit_menu.add_command(label='Paste', accelerator='Cmd+V', command=lambda: self.focus_get().event_generate('<<Paste>>'))
            edit_menu.add_command(label='Select All', accelerator='Cmd+A', command=lambda: self.focus_get().event_generate('<<SelectAll>>'))

            # 한글 입력기 호환성을 위한 직접 바인딩 (대소문자 모두 처리)
            # lambda event: ... 구문은 bind_all이 전달하는 불필요한 event 인수를 무시하기 위해 사용합니다.
            self.bind_all("<Command-s>", on_save_midi)
            self.bind_all("<Command-S>", on_save_midi)
            self.bind_all("<Command-c>", lambda event: self.focus_get().event_generate("<<Copy>>"))
            self.bind_all("<Command-C>", lambda event: self.focus_get().event_generate("<<Copy>>"))
            self.bind_all("<Command-v>", lambda event: self.focus_get().event_generate("<<Paste>>"))
            self.bind_all("<Command-V>", lambda event: self.focus_get().event_generate("<<Paste>>"))
            self.bind_all("<Command-x>", lambda event: self.focus_get().event_generate("<<Cut>>"))
            self.bind_all("<Command-X>", lambda event: self.focus_get().event_generate("<<Cut>>"))
            self.bind_all("<Command-a>", lambda event: self.focus_get().event_generate("<<SelectAll>>"))
            self.bind_all("<Command-A>", lambda event: self.focus_get().event_generate("<<SelectAll>>"))

        else:
            # 다른 OS에서는 기존의 단축키 바인딩 방식을 사용합니다.
            self._configure_shortcuts(on_save_midi)

    def _on_closing(self):
        """Handles window close event, ensuring the application terminates."""
        self.withdraw()  # Hide window for immediate user feedback
        try:
            # Cancel all pending after() jobs to prevent errors on exit
            for after_id in self.tk.eval('after info').split():
                self.after_cancel(after_id)
        except Exception:
            pass  # Ignore errors if interpreter is already shutting down

        try:
            self.destroy()
            if self.splash_root and self.splash_root.winfo_exists():
                self.splash_root.destroy()
        finally:
            # Force exit to prevent hanging process, which can happen with Tkinter errors on close.
            sys.exit(0)
        
    def _create_context_menu(self):
        menu = tk.Menu(self, tearoff=0); menu.add_command(label="Cut", command=lambda: self.focus_get().event_generate('<<Cut>>'))
        menu.add_command(label="Copy", command=lambda: self.focus_get().event_generate('<<Copy>>'))
        menu.add_command(label="Paste", command=lambda: self.focus_get().event_generate('<<Paste>>'))
        menu.add_separator(); menu.add_command(label="Select All", command=lambda: self.focus_get().event_generate('<<SelectAll>>'))
        return menu
    def _show_context_menu(self, event): self.context_menu.tk_popup(event.x_root, event.y_root)
    def _update_language(self, *_):
        self.lang_code = "en" if self.lang_var.get() == "English" else "ko"
        lang = self.i18n[self.lang_code]
        is_alpha_mode = self.mode_var.get() in [self.i18n["ko"]["alphabet"], self.i18n["en"]["alphabet"]]
        self.title(lang["title"])
        self.inherit_key_label = lang["inherit_key"]
        self.mode_btn.configure(values=[lang["alphabet"], lang["degree"]])
        self.mode_var.set(lang["alphabet"] if is_alpha_mode else lang["degree"])
        self.omit5_chk.configure(text=lang["omit5"])
        self.omit_bass_chk.configure(text=lang["omit_bass"])
        self.load_chart_btn.configure(text=lang["load_chart"])
        self.save_chart_btn.configure(text=lang["save_chart"])
        self.clear_all_btn.configure(text=lang["clear_all"])
        self.gen_btn.configure(text=lang["generate_midi"])
        self.builder_title_label.configure(text=lang["builder_title"])
        self.root_label.configure(text=lang["root"])
        self.quality_label.configure(text=lang["quality"])
        self.tensions_label.configure(text=lang["tensions"])
        self.reset_tensions_btn.configure(text=lang["reset_tensions"])
        self.insert_btn.configure(text=lang["build_insert"])

        self._rebuild_parts_ui()

        self.instructions.configure(state="normal")
        self.instructions.delete("1.0", "end")
        self.instructions.insert("1.0", lang["instructions_text"])
        self.instructions.configure(state="disabled")
        self._update_builder_roots()

    def _update_builder_roots(self):
        key = self._get_current_builder_key()
        is_degree_mode = self.mode_var.get() == self.i18n[self.lang_code]["degree"]
        if is_degree_mode:
            self.builder_root_menu.configure(values=App.roman_degrees_for_key(key))
            self.builder_root_var.set('I')
        else:
            use_sharps = App.prefers_sharps(key)
            self.builder_root_menu.configure(values=App.NOTE_NAMES_SHARP if use_sharps else App.NOTE_NAMES_FLAT)
            try:
                self.builder_root_var.set(App.pc_to_name(App.name_to_pc(self.builder_root_var.get()), use_sharps))
            except (ValueError, AttributeError):
                self.builder_root_var.set(App.pc_to_name(0, use_sharps))
    def _log(self, msg: str):
        try:
            self.log.configure(state="normal"); self.log.insert("end", msg + "\n"); self.log.see("end"); self.log.configure(state="disabled")
        except: pass
        try:
            with open(LOGFILE, "a", encoding="utf-8") as f: f.write(msg + "\n")
        except: pass
    def _set_focus_tracker(self, entry_widget):
        self.last_focused_entry = entry_widget
        self._update_builder_roots()
    
    # --- New UI Core Functions ---

    def _initialize_chart(self):
        """Sets up a default chart with one part and 16 measures."""
        self.parts_data = [{
            'part': '',
            'key': 'C',
            'measures': [''] * 16
        }]
        self._rebuild_parts_ui()

    def _rebuild_parts_ui(self):
        """Completely rebuilds the main scrolling area from `self.parts_data`."""
        if self._building:
            return
        self._building = True

        focused_widget = self.focus_get()
        yview = self.scroll.canvas.yview()

        self.main_area.grid_remove() # Hide before mass destruction/creation

        for widget in self.measures_frame.winfo_children():
            widget.destroy()

        self.measure_entries.clear()
        self.entry_part_map.clear()
        self.entry_global_idx_map.clear()
        self.part_widgets.clear()

        for part_idx, part_data in enumerate(self.parts_data):
            self._create_part_widgets(part_idx, part_data)

        self.add_part_btn = ctk.CTkButton(self.measures_frame, text="+ Add Part", command=self._add_part, fg_color="transparent", border_width=1)
        self.add_part_btn.pack(pady=10, padx=5, anchor="w")

        if self.measure_entries and self.last_focused_entry not in self.measure_entries:
            self.last_focused_entry = self.measure_entries[0]

        if isinstance(focused_widget, (ctk.CTkEntry, ctk.CTkOptionMenu)) and focused_widget.winfo_exists():
            self.after(10, focused_widget.focus_set)

        self.main_area.grid(row=2, column=0, padx=10, pady=5, sticky="nsew") # Restore visibility
        self.measures_frame.update_idletasks()
        self.scroll.canvas.configure(scrollregion=self.scroll.canvas.bbox("all"))
        if yview:
            self.after(50, lambda: self.scroll.canvas.yview_moveto(yview[0]))

        self._building = False
        self._log(f"UI rebuilt for {len(self.parts_data)} parts.")

    def _create_part_widgets(self, part_idx: int, part_data: Dict[str, Any]):
        """Creates and packs the UI for a single part."""
        lang = self.i18n[self.lang_code]

        part_frame = ctk.CTkFrame(self.measures_frame, border_width=1, fg_color=App.PART_GROUP_BG)
        part_frame.pack(pady=(0, 15), padx=5, fill="x", expand=True)

        header = ctk.CTkFrame(part_frame, fg_color="transparent")
        header.pack(fill="x", padx=10, pady=(8, 10))
        header.grid_columnconfigure(1, weight=1)

        part_var = tk.StringVar(master=self, value=part_data.get('part', ''))
        part_entry = ctk.CTkEntry(header, textvariable=part_var, placeholder_text=lang['part'], font=self.font_part_header, border_width=0, fg_color="transparent")
        part_entry.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 5))
        part_var.trace_add('write', lambda *_, p_idx=part_idx, var=part_var: self._update_part_data(p_idx, 'part', var.get()))

        key_label = ctk.CTkLabel(header, text=lang['key'], font=self.font_small_bold)
        key_label.grid(row=1, column=0, sticky="w", padx=(0, 5))

        key_var = tk.StringVar(master=self, value=part_data.get('key', 'C'))
        key_menu = ctk.CTkOptionMenu(header, variable=key_var, values=App.KEYS, command=lambda val, p_idx=part_idx: self._on_part_key_changed(p_idx, val), height=24, font=self.font_small, dropdown_font=self.font_small)
        key_menu.grid(row=1, column=1, sticky="w")

        header.grid_columnconfigure(2, weight=1)

        measure_controls_frame = ctk.CTkFrame(header, fg_color="transparent")
        measure_controls_frame.grid(row=0, rowspan=2, column=2, sticky="e", padx=(10, 0))

        measures_entry = ctk.CTkEntry(measure_controls_frame, width=45, height=24, font=self.font_main, justify="center")
        measures_entry.insert(0, "4")

        sub_btn = ctk.CTkButton(measure_controls_frame, text="-", width=30, height=24, font=self.font_main, command=lambda p_idx=part_idx, e=measures_entry: self._decrease_measures(p_idx, e))
        sub_btn.pack(side="left")

        measures_entry.pack(side="left", padx=4)

        add_btn = ctk.CTkButton(measure_controls_frame, text="+", width=30, height=24, font=self.font_main, command=lambda p_idx=part_idx, e=measures_entry: self._increase_measures(p_idx, e))
        add_btn.pack(side="left")

        delete_btn = ctk.CTkButton(header, text="🗑️", width=30, height=24, fg_color="transparent", text_color=("gray10", "gray90"), hover_color=("#E53935", "#B71C1C"), command=lambda p_idx=part_idx: self._delete_part(p_idx))
        delete_btn.grid(row=0, rowspan=2, column=3, sticky="e", padx=(10,0))

        measures_grid = ctk.CTkFrame(part_frame, fg_color="transparent")
        measures_grid.pack(fill="x", padx=10, pady=(0, 10))

        measures = part_data.get('measures', [])
        for i, measure_text in enumerate(measures):
            self._create_measure_cell(measures_grid, part_idx, i, measure_text)

        self.part_widgets.append({
            'part_frame': part_frame,
            'measures_grid': measures_grid,
            'delete_button': delete_btn,
            'add_button': add_btn,
            'sub_button': sub_btn,
            'measures_entry': measures_entry
        })

    def _create_measure_cell(self, parent_grid: ctk.CTkFrame, part_idx: int, measure_idx_in_part: int, measure_text: str, insert_index: Optional[int] = None):
        """Creates and packs the UI for a single measure cell."""
        row, col = divmod(measure_idx_in_part, 4)
        if col == 0:
            parent_grid.grid_rowconfigure(row, pad=5)

        cell_color = self._get_measure_cell_color()
        border_color = ctk.ThemeManager.theme['CTkFrame']['border_color']
        cell_frame = ctk.CTkFrame(parent_grid, border_width=1, border_color=border_color, fg_color=cell_color)
        cell_frame.grid(row=row, column=col, padx=(0,5))
        cell_frame.grid_columnconfigure(1, weight=1)

        label = ctk.CTkLabel(cell_frame, text=str(measure_idx_in_part + 1), font=self.font_small_bold, width=20)
        label.grid(row=0, column=0, padx=(4, 0), pady=2)

        entry = ctk.CTkEntry(cell_frame, font=self.font_measure_entry, border_width=0, fg_color='transparent', width=115)
        entry.grid(row=0, column=1, padx=(4, 6), pady=2, sticky='ew')
        entry.insert(0, measure_text)

        entry.bind('<FocusIn>', lambda event, e=entry: self._set_focus_tracker(e))
        entry.bind('<Button-3>', self._show_context_menu)
        entry.bind('<FocusOut>', lambda event, p_idx=part_idx, m_idx=measure_idx_in_part, e=entry: self._update_part_data(p_idx, f'measures.{m_idx}', e.get()))

        # Update global trackers
        global_measure_idx = sum(len(p.get('measures', [])) for p in self.parts_data[:part_idx]) + measure_idx_in_part
        if insert_index is None or insert_index >= len(self.measure_entries):
            self.measure_entries.append(entry)
        else:
            self.measure_entries.insert(insert_index, entry)
        self.entry_part_map[entry] = part_idx
        self.entry_global_idx_map[entry] = global_measure_idx

    def _get_measure_cell_color(self) -> str:
        """Gets the appropriate background color for a measure cell."""
        frame_theme = ctk.ThemeManager.theme.get('CTkFrame', {})
        color = frame_theme.get('top_fg_color', frame_theme.get('fg_color', 'transparent'))
        return self._apply_appearance_mode(color) if isinstance(color, (tuple, list)) else color

    # --- Part and Measure Data Manipulation ---

    def _add_part(self):
        """Adds a new part to the chart incrementally."""
        last_key = self.parts_data[-1]['key'] if self.parts_data else 'C'
        new_part_data = {'part': '', 'key': last_key, 'measures': [''] * 8}
        self.parts_data.append(new_part_data)
        
        part_idx = len(self.parts_data) - 1

        if self.add_part_btn:
            self.add_part_btn.pack_forget()

        self._create_part_widgets(part_idx, new_part_data)
        
        if self.add_part_btn:
            self.add_part_btn.pack(pady=10, padx=5, anchor="w")

        self._update_scroll_region_and_view(1.0)
        self._log("Added a new part.")

    def _delete_part(self, part_idx: int):
        """Deletes a part from the chart incrementally for better performance."""
        if len(self.parts_data) <= 1:
            self.parts_data[0]['part'] = ''
            self.parts_data[0]['measures'] = [''] * 4
            self._rebuild_parts_ui()
            self._log("Last part has been cleared.")
            return

        # 1. 삭제할 파트의 UI 프레임을 미리 찾아둡니다.
        part_widget_group = self.part_widgets[part_idx]
        frame_to_destroy = part_widget_group['part_frame']
        
        # 2. [수정된 부분] entry_part_map을 이용해 삭제할 파트에 속한 모든 Entry 위젯을 찾습니다.
        entries_to_remove = [entry for entry, p_idx in self.entry_part_map.items() if p_idx == part_idx]
        
        # 3. 파트 데이터와 위젯 참조 정보를 리스트에서 제거합니다.
        self.parts_data.pop(part_idx)
        self.part_widgets.pop(part_idx)
        
        # 4. 찾아둔 마디 Entry들을 추적 리스트와 맵에서 제거합니다.
        for entry in entries_to_remove:
            if entry in self.measure_entries:
                self.measure_entries.remove(entry)
            if entry in self.entry_part_map:
                del self.entry_part_map[entry]
            if entry in self.entry_global_idx_map:
                del self.entry_global_idx_map[entry]

        # 5. 파트의 프레임을 화면에서 제거합니다.
        frame_to_destroy.destroy()
        
        # 6. 삭제된 파트보다 뒤에 있던 파트들의 인덱스를 1씩 줄여줍니다.
        for entry, p_idx in self.entry_part_map.items():
            if p_idx > part_idx:
                self.entry_part_map[entry] = p_idx - 1
        
        # 7. 전체 마디의 전역 인덱스를 다시 정리합니다.
        for i in range(part_idx, len(self.part_widgets)):
            new_part_idx = i
            widgets_to_update = self.part_widgets[i]
            measures_entry = widgets_to_update['measures_entry']

            # Re-bind commands with the new, correct part index
            widgets_to_update['delete_button'].configure(command=lambda p_idx=new_part_idx: self._delete_part(p_idx))
            widgets_to_update['add_button'].configure(command=lambda p_idx=new_part_idx, e=measures_entry: self._increase_measures(p_idx, e))
            widgets_to_update['sub_button'].configure(command=lambda p_idx=new_part_idx, e=measures_entry: self._decrease_measures(p_idx, e))

        for i, entry in enumerate(self.measure_entries):
             self.entry_global_idx_map[entry] = i

        # 8. 스크롤 영역을 업데이트합니다.
        self._update_scroll_region_and_view()
        self._log(f"Part at index {part_idx} deleted incrementally.")

    def _increase_measures(self, part_idx: int, entry_widget: ctk.CTkEntry):
        """Adds measures to the specified part (defaults to the last part)."""
        if not self.parts_data:
            self._initialize_chart()
            return


        if not (0 <= part_idx < len(self.parts_data)) or part_idx >= len(self.part_widgets):
            return

        try:
            step = int(entry_widget.get())
        except (ValueError, TypeError):
            step = 4

        step = max(1, step)

        part_widgets = self.part_widgets[part_idx]
        measures_grid = part_widgets['measures_grid']

        old_num_measures = len(self.parts_data[part_idx]['measures'])
        self.parts_data[part_idx]['measures'].extend([''] * step)

        insert_index = sum(len(p.get('measures', [])) for p in self.parts_data[:part_idx]) + old_num_measures

        for i in range(step):
            measure_idx_in_part = old_num_measures + i
            self._create_measure_cell(
                measures_grid,
                part_idx,
                measure_idx_in_part,
                "",
                insert_index=insert_index + i
            )

        for entry, entry_part in self.entry_part_map.items():
            if entry_part > part_idx:
                current_idx = self.entry_global_idx_map.get(entry)
                if current_idx is not None:
                    self.entry_global_idx_map[entry] = current_idx + step

        self._update_scroll_region_and_view()
        self._log(f"Added {step} measures to part {part_idx + 1}.")

    def _decrease_measures(self, part_idx: int, entry_widget: ctk.CTkEntry):
        """Removes measures from the specified part incrementally."""
        if not self.parts_data or not (0 <= part_idx < len(self.parts_data)):
            return
        try:
            step = int(entry_widget.get())
        except (ValueError, TypeError):
            step = 4

        step = max(1, step)

        target_part_measures = self.parts_data[part_idx]['measures']
        old_len = len(target_part_measures)
        new_len = max(4, old_len - step)
        
        if new_len == old_len:
            return

        removed_count = old_len - new_len
        
        measures_grid = self.part_widgets[part_idx]['measures_grid']
        all_cells = measures_grid.winfo_children()
        cells_to_remove = all_cells[new_len:]

        entries_to_remove = []
        
        for cell in cells_to_remove:
            entry_to_remove = next((w for w in cell.winfo_children() if isinstance(w, ctk.CTkEntry)), None)
            if entry_to_remove:
                entries_to_remove.append(entry_to_remove)
            cell.destroy()
            
        for entry in entries_to_remove:
            if entry in self.measure_entries: self.measure_entries.remove(entry)
            if entry in self.entry_part_map: del self.entry_part_map[entry]
            if entry in self.entry_global_idx_map: del self.entry_global_idx_map[entry]

        self.parts_data[part_idx]['measures'] = target_part_measures[:new_len]

        for entry, entry_part_idx in self.entry_part_map.items():
            if entry_part_idx > part_idx:
                current_idx = self.entry_global_idx_map.get(entry)
                if current_idx is not None:
                    self.entry_global_idx_map[entry] = current_idx - removed_count
        
        self._update_scroll_region_and_view()
        if removed_count > 0:
            self._log(f"Removed {removed_count} measures from part {part_idx + 1}.")

    def _update_part_data(self, part_idx: int, key_path: str, value: Any):
        """Updates data in self.parts_data without triggering a full rebuild."""
        if self._building: return
        try:
            if '.' in key_path:
                key, index_str = key_path.split('.')
                index = int(index_str)
                if self.parts_data[part_idx][key][index] != value:
                    self.parts_data[part_idx][key][index] = value
            else:
                if self.parts_data[part_idx][key_path] != value:
                    self.parts_data[part_idx][key_path] = value
        except (IndexError, KeyError) as e:
            self._log(f"Error updating part data: {e}")

    def _update_scroll_region_and_view(self, y_moveto: Optional[float] = None):
        """Updates the scroll region and optionally moves the view."""
        self.measures_frame.update_idletasks()
        self.scroll.canvas.configure(scrollregion=self.scroll.canvas.bbox("all"))
        if y_moveto is not None:
            self.after(50, lambda: self.scroll.canvas.yview_moveto(y_moveto))

    def _configure_shortcuts(self, save_handler):
        """Registers global shortcuts for non-macOS platforms."""
        modifier = "Control"

        # Save Shortcut
        self.bind_all(f"<{modifier}-s>", save_handler, add="+")
        self.bind_all(f"<{modifier}-S>", save_handler, add="+")

        # On Windows/Linux, standard copy/paste shortcuts are generally handled
        # by the default widget bindings, so no extra bindings are needed here.

    # --- End of New UI Core Functions ---

    def _get_row_key_options(self) -> List[str]:
        return [self.inherit_key_label] + App.KEYS

    def _display_key_value(self, value: str) -> str:
        value = (value or "").strip()
        return value if value else self.inherit_key_label

    def _extract_key_value(self, display_value: str) -> str:
        value = (display_value or "").strip()
        return "" if not value or value == self.inherit_key_label else value

    def _get_key_for_measure_index(self, index: int) -> str:
        if index is None or index < 0:
            return "C"
        
        current_pos = 0
        for part_data in self.parts_data:
            num_measures = len(part_data.get('measures', []))
            if current_pos <= index < current_pos + num_measures:
                return part_data.get('key') or 'C'
            current_pos += num_measures
        
        if self.parts_data:
            return self.parts_data[-1].get('key') or 'C'
        return "C"

    def _get_key_for_entry(self, entry: ctk.CTkEntry) -> str:
        if entry is None:
            return self.parts_data[0].get('key', 'C') if self.parts_data else "C"
        
        if entry in self.entry_part_map:
            part_idx = self.entry_part_map[entry]
            if 0 <= part_idx < len(self.parts_data):
                return self.parts_data[part_idx].get('key', 'C')

        return self._get_current_builder_key()

    def _get_current_builder_key(self) -> str:
        if self.last_focused_entry:
            return self._get_key_for_entry(self.last_focused_entry)
        return self.parts_data[0].get('key', 'C') if self.parts_data else "C"

    def _on_part_key_changed(self, part_idx: int, new_key: str):
        if self._building: return
        self._update_part_data(part_idx, 'key', new_key)
        if not self._suppress:
            self._convert_all_entries()
        self._update_builder_roots()

    def _clear_all_chords(self):
        lang = self.i18n[self.lang_code]
        if messagebox.askyesno(lang["clear_confirm_title"], lang["clear_confirm_message"]):
            self._initialize_chart()
            self._log("All parts and measures cleared.")

    def _on_mode_changed(self, *_):
        if self._suppress: return
        self._log(f"Mode changed to {self.mode_var.get()}. "); self._update_builder_roots(); self._convert_all_entries()

    def _convert_all_entries(self):
        mode = self.mode_var.get()
        is_to_degree = (mode == self.i18n[self.lang_code]["degree"])
        for entry in getattr(self, "measure_entries", []):
            text = entry.get().strip()
            if not text:
                continue
            key = self._get_key_for_entry(entry)
            parts = App.split_measure_text(text)
            output_parts: List[str] = []
            for part_text in parts:
                if part_text == "%":
                    output_parts.append(part_text)
                    continue
                try:
                    parsed = App.parse_chord_symbol(part_text, key)
                    converted = App.build_string_from_parsed(parsed, is_roman=is_to_degree, key=key)
                    output_parts.append(converted)
                except Exception as ex:
                    self._log(f"Conversion error on '{part_text}' (key {key}): {ex}")
            entry.delete(0, "end")
            if output_parts:
                entry.insert(0, " ".join(output_parts))

    def _reset_tensions(self):
        for var in self.tension_vars.values(): var.set(False)
        self._log("Tension selection reset.")

    def _on_build_and_insert(self):
        target = self.last_focused_entry or (self.measure_entries[0] if self.measure_entries else None)
        if not target:
            self._log("No measure entry to insert into.")
            return

        key = self._get_key_for_entry(target)
        root_selection = self.builder_root_var.get()
        qual = self.builder_quality_var.get()
        selected_tensions = [t for t, v in self.tension_vars.items() if v.get()]
        
        qual_txt = qual if qual not in ["Major", "Minor"] else ('m' if qual == "Minor" else '')
        
        paren_tensions = [t for t in selected_tensions if re.search(r'[b#]', t)]
        text_tensions = [t for t in selected_tensions if not re.search(r'[b#]', t)]
        
        tens_txt = "".join(sorted(text_tensions, key=lambda x: int(re.sub(r'[^0-9]', '', x))))
        if selected_tensions and not any(c in qual_txt for c in ['7','M','M','m','d','a','s']):
            if not tens_txt: tens_txt = '7'
            
        paren_txt = f"({','.join(paren_tensions)})" if paren_tensions else ''
            
        chord_str_to_parse = f"{root_selection}{qual_txt}{tens_txt}{paren_txt}"
        
        parsed = App.parse_chord_symbol(chord_str_to_parse, key)
        is_degree_mode = self.mode_var.get() == self.i18n[self.lang_code]["degree"]
        sym = App.build_string_from_parsed(parsed, is_roman=is_degree_mode, key=key)

        cur = target.get().strip()
        target.delete(0, "end")
        target.insert(0, (cur + " " + sym).strip())
        self._log(f"Inserted chord: {sym}")
        
        # Update data model
        if target in self.entry_part_map:
            part_idx = self.entry_part_map[target]
            # Find measure index within the part
            part_entries = [e for e in self.measure_entries if self.entry_part_map.get(e) == part_idx]
            try:
                measure_idx_in_part = part_entries.index(target)
                self._update_part_data(part_idx, f'measures.{measure_idx_in_part}', target.get())
            except ValueError:
                pass

    def _on_generate_midi(self):
        try:
            path = filedialog.asksaveasfilename(title="Save MIDI",defaultextension=".mid", filetypes=[("MIDI file", "*.mid")])
            if not path: self._log("Save cancelled."); return
            mid = MidiFile(ticks_per_beat=480); track = MidiTrack(); mid.tracks.append(track)
            tpb = mid.ticks_per_beat; track.append(MetaMessage('set_tempo', tempo=bpm2tempo(120)))
            
            initial_key = self.parts_data[0]['key'] if self.parts_data else "C"
            try:
                track.append(MetaMessage("key_signature", key=initial_key))
            except Exception:
                self._log(f"Skipping key_signature for '{initial_key}' (unsupported)")

            last_resolved_chord: Optional[str] = None
            for entry in getattr(self, "measure_entries", []):
                idx = self.entry_global_idx_map.get(entry)
                if idx is None: continue

                txt = entry.get().strip()
                key = self._get_key_for_measure_index(idx)
                if not txt:
                    track.append(Message('note_off', note=0, velocity=0, time=4 * tpb))
                    continue

                chord_tokens = App.split_measure_text(txt)
                durations = App.duration_ticks_for_n(len(chord_tokens), tpb)
                for i, token in enumerate(chord_tokens):
                    resolved = token
                    if token == "%":
                        resolved = last_resolved_chord
                    if not resolved:
                        track.append(Message('note_off', note=0, velocity=0, time=durations[i]))
                        continue
                    try:
                        parsed = App.parse_chord_symbol(resolved, key)
                        notes = App.build_voicing(parsed, omit5_on_conflict=self.omit5_var.get(), omit_duplicated_bass=self.omit_bass_var.get())
                        chord_duration = durations[i]
                        for note_val in notes:
                            track.append(Message('note_on', note=note_val, velocity=80, time=0))
                        for j, note_val in enumerate(notes):
                            track.append(Message('note_off', note=note_val, velocity=0, time=chord_duration if j == 0 else 0))
                        last_resolved_chord = resolved
                    except Exception as chord_err:
                        self._log(f"Skipping invalid chord '{resolved}': {chord_err}")
                        track.append(Message('note_off', note=0, velocity=0, time=durations[i]))
            mid.save(path); self._log(f"Saved MIDI: {path}"); messagebox.showinfo("MIDI", f"Saved: {path}")
        except Exception as e:
            self._log(f"FATAL Error generating MIDI: {e}"); messagebox.showerror("Error", f"Failed to generate MIDI:\n{e}")

    def _serialize_chart(self) -> str:
        """Serializes the current chart data into a string for saving."""
        lines: List[str] = []
        for part_data in self.parts_data:
            part_name = part_data.get('part', '').strip()
            key = part_data.get('key', '').strip()
            
            header_bits: List[str] = []
            if part_name:
                header_bits.append(f"[{part_name}]")
            if key:
                header_bits.append(f"(Key:{key})")
            
            if header_bits:
                lines.append(" ".join(header_bits).strip())
                
            measures = part_data.get('measures', [])
            for i in range(0, len(measures), 4):
                chunk = measures[i:i+4]
                measure_line = " | ".join(m.strip() for m in chunk)
                lines.append(f"| {measure_line} |")
            
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def _apply_parsed_chart(self, parsed_rows: List[Dict[str, Any]]):
        """Applies parsed chart data to the UI."""
        if not parsed_rows:
            self._initialize_chart()
            return

        new_parts_data: List[Dict[str, Any]] = []
        current_part_data: Optional[Dict[str, Any]] = None

        def commit_part():
            if current_part_data:
                # Clean up trailing empty measures
                while current_part_data["measures"] and not current_part_data["measures"][-1]:
                    current_part_data["measures"].pop()
                # Only add part if it has content
                if current_part_data["measures"]:
                    new_parts_data.append(current_part_data)

        last_key = "C"
        for row in parsed_rows:
            is_new_part = bool(row.get("part"))
            if not is_new_part and row.get("key") and current_part_data:
                 if row.get("key") != current_part_data.get("key"):
                     is_new_part = True

            if is_new_part or not current_part_data:
                commit_part()
                current_part_data = {
                    "part": row.get("part", ""),
                    "key": row.get("key", "") or last_key,
                    "measures": []
                }
            
            if current_part_data:
                current_part_data["measures"].extend(row.get("measures", []))
                last_key = current_part_data["key"]

        commit_part()

        if not new_parts_data:
            self._initialize_chart()
            return

        self.parts_data = new_parts_data
        self._rebuild_parts_ui()
        self._log(f"Loaded chart with {len(self.parts_data)} parts.")

    def _parse_chart_text(self, text: str) -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        current_part = ""
        current_key_effective = ""
        pending_row_key: Optional[str] = None
        display_part_next_row = False
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            part_key_match = re.match(r"^\[(?P<part>[^\]]*)\]\s*(?P<rest>.*)$", line)
            if part_key_match:
                part_text = part_key_match.group("part").strip()
                rest = part_key_match.group("rest").strip()
                comment = re.sub(r"\(\s*Key\s*:\s*[^\)]+\)", "", rest).strip()
                current_part = (f"{part_text} {comment}".strip()) if comment else part_text
                key_match = re.search(r"\(\s*Key\s*:\s*([^\)]+)\)", rest)
                if key_match:
                    current_key_effective = key_match.group(1).strip()
                    pending_row_key = current_key_effective
                else:
                    pending_row_key = None
                display_part_next_row = True
                continue
            key_only_match = re.match(r"^\(\s*Key\s*:\s*([^\)]+)\)\s*$", line)
            if key_only_match:
                current_key_effective = key_only_match.group(1).strip()
                pending_row_key = current_key_effective
                continue
            if line.startswith('|'):
                segments = [seg.strip() for seg in line.strip('|').split('|')]
                while len(segments) < 4:
                    segments.append("")
                rows.append({
                    "part": current_part if display_part_next_row else "",
                    "key": (pending_row_key or ""),
                    "measures": segments[:4],
                })
                if pending_row_key is not None:
                    current_key_effective = pending_row_key
                pending_row_key = None
                display_part_next_row = False
                continue
        return rows

    def _load_chart_from_file(self):
        path = filedialog.askopenfilename(title="Load Chart", filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")])
        if not path:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
        except OSError as err:
            messagebox.showerror("Error", f"Failed to read file:\n{err}")
            return
        parsed_rows = self._parse_chart_text(content)
        if not parsed_rows:
            messagebox.showwarning("Warning", "No chart data found in the selected file.")
            return
        self._apply_parsed_chart(parsed_rows)
        self._log(f"Loaded chart from {path}")

    def _save_chart_to_file(self):
        text_content = self._serialize_chart()
        path = filedialog.asksaveasfilename(title="Save Chart", defaultextension=".txt", filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")])
        if not path:
            return
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(text_content)
        except OSError as err:
            messagebox.showerror("Error", f"Failed to save file:\n{err}")
            return
        self._log(f"Saved chart to {path}")

if __name__ == "__main__":
    def _escape_for_py(value: str) -> str:
        """Escapes a string for safe inclusion in a Python multiline string."""
        return (value
                .replace("\\", "\\\\")
                .replace("'", "\\'")  
                .replace('"', '\\"')
                .replace('{', '{{')
                .replace('}', '}}'))    
    from pathlib import Path
    import sys
    import os
    import logging
    import shutil
    import re
    import requests
    import hashlib
    import subprocess
    import time
    import platform
    import tarfile
    import textwrap
    import webbrowser  # webbrowser 라이브러리 추가
    from packaging.version import parse as parse_version
    from tuf.ngclient import Updater
    from tuf.ngclient.config import UpdaterConfig

    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger('tuf').setLevel(logging.DEBUG)

    try:
        APP_NAME = 'Chord-to-MIDI-GENERATOR'
        writable_dir = Path.home() / f'.{APP_NAME.lower().replace(" ", "_")}'
        writable_dir.mkdir(parents=True, exist_ok=True)

        lock_file_path = writable_dir / 'app.lock'
        if not acquire_single_instance_lock(str(lock_file_path)):
            notify_instance_already_running(
                "Chord to MIDI Generator is already running.\n\n앱이 이미 실행 중입니다. 실행 중인 창을 먼저 종료해 주세요."
            )
            sys.exit(0)

        update_flag_path = writable_dir / 'update_in_progress'
        if update_flag_path.exists():
            notify_instance_already_running(
                "An update is currently in progress. Please wait for it to finish.\n\n업데이트가 진행 중입니다. 완료될 때까지 잠시 기다려 주세요."
            )
            sys.exit(0)

        metadata_dir = writable_dir / 'metadata'
        
        # Force update check by clearing cache
        if metadata_dir.exists():
            shutil.rmtree(metadata_dir)
        os.makedirs(metadata_dir, exist_ok=True)
        
        bundled_root_json_path_str = App.resource_path('root.json')
        shutil.copy(bundled_root_json_path_str, metadata_dir / 'root.json')

        # ---- 수정된 부분: app_install_dir 정의 위치 변경 ----
        # PyInstaller로 빌드되었는지 여부에 따라 앱 설치 경로를 결정
        if getattr(sys, 'frozen', False):
            app_executable_path = Path(sys.executable)
            if sys.platform == "darwin":
                # macOS .app bundle structure: AppName.app/Contents/MacOS/AppName
                app_install_dir = app_executable_path.parent.parent.parent
            else:
                # Windows/Linux frozen structure: directory/AppName.exe
                app_install_dir = app_executable_path.parent
        else:
            # 일반 파이썬 스크립트로 실행될 경우
            app_install_dir = Path(__file__).parent
        # ---------------------------------------------------
        
        METADATA_BASE_URL = 'https://kimtopseong.github.io/Chord-to-MIDI-GENERATOR/metadata'
        target_dir = writable_dir / 'targets'
        os.makedirs(target_dir, exist_ok=True)
        
        updater = Updater(
            metadata_dir=str(metadata_dir),
            metadata_base_url=METADATA_BASE_URL,
            target_dir=str(target_dir),
            target_base_url="", # This remains empty as TUF's download isn't used.
            config=UpdaterConfig(max_root_rotations=10)
        )
        updater.refresh() 
        
        latest_target = None
        latest_version_str = CURRENT_VERSION

        trusted_set = updater._trusted_set
        all_targets = trusted_set.targets.targets
        
        for target_name, target_info in all_targets.items():
            match = re.search(r'-(\d+\.\d+\.\d+)\.tar\.gz$', target_name)
            if match:
                version_str = match.group(1)
                if parse_version(version_str) > parse_version(latest_version_str):
                    latest_version_str = version_str
                    latest_target = target_info

        if latest_target and parse_version(latest_version_str) > parse_version(CURRENT_VERSION):
            title = f"업데이트 가능 (Update Available) v{latest_version_str}"
            message = (
                f"새로운 {latest_version_str} 버전으로 업데이트할 수 있습니다. 설치하시겠습니까?\n"
                f"---\n"
                f"An update to version {latest_version_str} is available. Do you want to install it?"
            )
            if messagebox.askyesno(title, message):
                
                tmp_path = None
                progress_window = None
                status_file_path = None
                progress_helper_path = None
                progress_helper_ps_path = None
                progress_helper_proc = None
                update_script_started = False
                try:
                    progress_window = UpdateProgressWindow()
                    progress_window.update_status("업데이트 다운로드 준비 중...", 0)

                    tag_name = f"v{latest_version_str}"
                    file_name = os.path.basename(latest_target.path)
                    base_url = "https://github.com/kimtopseong/Chord-to-MIDI-GENERATOR/releases/download"
                    download_url = f"{base_url}/{tag_name}/{file_name}"
                    print(f"Downloading update from: {download_url}")

                    resp = requests.get(download_url, stream=True, timeout=(5, 120))
                    resp.raise_for_status()

                    tmp_path = os.path.join(str(target_dir), f".{file_name}.part")
                    hasher = hashlib.sha256()
                    total_bytes = 0
                    expected_len = latest_target.length or 0

                    if expected_len:
                        progress_window.update_status(
                            f"다운로드 중... (0 / {format_bytes(expected_len)})", 0
                        )
                    else:
                        progress_window.update_status("다운로드 중...", None)

                    with open(tmp_path, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=1024 * 1024):
                            if not chunk:
                                continue
                            f.write(chunk)
                            hasher.update(chunk)
                            total_bytes += len(chunk)

                            if expected_len:
                                percent = (total_bytes / expected_len) * 100
                                progress_window.update_status(
                                    f"다운로드 중... ({format_bytes(total_bytes)} / {format_bytes(expected_len)})",
                                    percent,
                                )

                    if expected_len and total_bytes != expected_len:
                        raise ValueError(f"Length mismatch: expected {expected_len}, got {total_bytes}")

                    downloaded_hash = hasher.hexdigest()
                    trusted_hash = latest_target.hashes.get("sha256")
                    if downloaded_hash.lower() != str(trusted_hash).lower():
                        raise ValueError(f"Hash mismatch! Trusted: {trusted_hash}, Downloaded: {downloaded_hash}")

                    print("File hash & length verified successfully.")
                    progress_window.update_status("다운로드 검증 중...", 100)

                    final_path = os.path.join(str(target_dir), file_name)
                    os.replace(tmp_path, final_path)
                    tmp_path = None

                    updater_log_path = os.path.join(writable_dir, 'updater.log')
                    progress_window.update_status("설치 파일 준비 중...", None)

                    status_file_path = os.path.join(str(writable_dir), 'update_status.txt')
                    progress_helper_path = os.path.join(str(writable_dir), '_update_progress.py')
                    progress_helper_ps_path = os.path.join(str(writable_dir), '_update_progress.ps1')

                    for stale_path in (status_file_path, progress_helper_path, progress_helper_ps_path):
                        if stale_path and os.path.exists(stale_path):
                            try:
                                os.remove(stale_path)
                            except OSError:
                                pass

                    def _write_status_snapshot(state: str, percent: int, message: str) -> None:
                        try:
                            safe_msg = message.replace('\n', ' ').replace('|', '/')
                            with open(status_file_path, 'w', encoding='utf-8') as status_file:
                                status_file.write(f"{state}|{percent}|{safe_msg}")
                        except OSError:
                            pass

                    _write_status_snapshot('preparing', 5, '설치 파일 준비 중... (Preparing installer...)')

                    try:
                        with open(update_flag_path, 'w', encoding='utf-8') as flag_file:
                            flag_file.write(str(int(time.time())))
                    except OSError:
                        pass

                    helper_title = "Chord to MIDI Update"
                    helper_message = "업데이트가 진행 중입니다...\nInstalling update..."

                    if sys.platform == "darwin":
                        progress_helper_path = os.path.join(str(writable_dir), '_update_progress.py')
                    elif sys.platform == "win32":
                        progress_helper_ps_path = os.path.join(str(writable_dir), '_update_progress.ps1')

                    try:
                        if sys.platform == "darwin":
                            escaped_status_for_py = _escape_for_py(status_file_path)
                            escaped_title_for_py = helper_title.replace('"', '\\"')
                            escaped_message_for_py = _escape_for_py(helper_message)
                            progress_helper_template = textwrap.dedent("""\
import os
import sys
import time
import tkinter as tk
from tkinter import ttk

STATUS_PATH = r"{status_path}"
WINDOW_TITLE = "{window_title}"
INITIAL_MESSAGE = "{initial_message}"


def read_status():
    if not os.path.exists(STATUS_PATH):
        return None
    try:
        with open(STATUS_PATH, 'r', encoding='utf-8') as status_file:
            line = status_file.read().strip()
    except OSError:
        return None
    if not line:
        return None
    parts = line.split('|', 2)
    if len(parts) < 3:
        return None
    state, percent_str, message = parts
    try:
        percent_val = int(percent_str)
    except ValueError:
        percent_val = -1
    return state, percent_val, message


class ProgressUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(WINDOW_TITLE)
        self.root.geometry('360x150')
        self.root.resizable(False, False)
        self.root.attributes('-topmost', True)
        self.label = tk.Label(self.root, text=INITIAL_MESSAGE, font=('Helvetica', 12), justify='center')
        self.label.pack(pady=(24, 12))
        self.progress = ttk.Progressbar(self.root, orient='horizontal', mode='indeterminate', length=260)
        self.progress.pack(pady=4)
        self.note = tk.Label(self.root, text='창을 닫지 마세요 (Do not close this window)', font=('Helvetica', 10))
        self.note.pack(pady=(0, 8))
        self.progress.start(12)
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)
        self._done_scheduled = False
        self._last_state = None
        self.root.after(250, self._poll)

    def _on_close(self):
        if self._last_state in ('done', 'error'):
            self.root.destroy()

    def _set_determinate(self):
        if self.progress['mode'] != 'determinate':
            self.progress.stop()
            self.progress.config(mode='determinate')

    def _set_indeterminate(self):
        if self.progress['mode'] != 'indeterminate':
            self.progress.config(mode='indeterminate')
            self.progress.start(12)

    def _update_ui(self, state, percent, message):
        self._last_state = state
        self.label.config(text=message)
        if percent is not None and percent >= 0:
            self._set_determinate()
            self.progress['value'] = max(0, min(100, percent))
        else:
            self._set_indeterminate()
        if state == 'done':
            self._set_determinate()
            self.progress['value'] = 100
            if not self._done_scheduled:
                self._done_scheduled = True
                self.root.after(1200, self.root.destroy)
        elif state == 'error':
            self._set_determinate()
            self.progress['value'] = 0

    def _poll(self):
        status = read_status()
        if not status:
            if not self._done_scheduled:
                self._done_scheduled = True
                self.root.after(600, self.root.destroy)
            return
        state, percent, message = status
        self._update_ui(state, percent, message)
        self.root.after(350, self._poll)


def fallback_console():
    last_state = None
    while True:
        status = read_status()
        if status:
            state, percent, message = status
            if state != last_state:
                sys.stdout.write('[update] %s %s%% %s\n' % (state, percent, message))
                sys.stdout.flush()
                last_state = state
            if state in ('done', 'error'):
                break
        time.sleep(0.5)


def main():
    try:
        ui = ProgressUI()
    except Exception:
        fallback_console()
        return
    ui.root.mainloop()


if __name__ == '__main__':
    os.environ.setdefault('TK_SILENCE_DEPRECATION', '1')
    main()
""")

                            with open(progress_helper_path, 'w', encoding='utf-8') as helper_file:
                                helper_file.write(progress_helper_template.format(
                                    status_path=escaped_status_for_py,
                                    window_title=escaped_title_for_py,
                                    initial_message=escaped_message_for_py,
                                ))

                            helper_env = os.environ.copy()
                            helper_env.setdefault('TK_SILENCE_DEPRECATION', '1')
                            progress_helper_proc = subprocess.Popen(
                                ['/usr/bin/python3', progress_helper_path],
                                env=helper_env,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                            )
                        elif sys.platform == "win32":
                            helper_message_ps = helper_message.replace('`', '``')
                            helper_title_ps = helper_title.replace('`', '``')
                            status_path_ps = status_file_path.replace('`', '``')
                            progress_helper_template = textwrap.dedent("""\
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$StatusPath = '{status_path}'
$WindowTitle = '{window_title}'
$InitialMessage = @'
{initial_message}
'@

[System.Windows.Forms.Application]::EnableVisualStyles()
$form = New-Object System.Windows.Forms.Form
$form.Text = $WindowTitle
$form.StartPosition = 'CenterScreen'
$form.Size = New-Object System.Drawing.Size(380,170)
$form.TopMost = $true

$label = New-Object System.Windows.Forms.Label
$label.Text = $InitialMessage
$label.AutoSize = $false
$label.TextAlign = 'MiddleCenter'
$label.Font = New-Object System.Drawing.Font('Segoe UI',12,[System.Drawing.FontStyle]::Regular)
$label.Size = New-Object System.Drawing.Size(340,60)
$label.Location = New-Object System.Drawing.Point(20,15)
$form.Controls.Add($label)

$progress = New-Object System.Windows.Forms.ProgressBar
$progress.Style = 'Marquee'
$progress.Location = New-Object System.Drawing.Point(20,90)
$progress.Size = New-Object System.Drawing.Size(340,20)
$form.Controls.Add($progress)

$note = New-Object System.Windows.Forms.Label
$note.Text = '창을 닫지 마세요 (Do not close this window)'
$note.AutoSize = $false
$note.TextAlign = 'MiddleCenter'
$note.Size = New-Object System.Drawing.Size(340,20)
$note.Location = New-Object System.Drawing.Point(20,115)
$form.Controls.Add($note)

$script:doneTimer = $null

function Set-Status {{
    param($state, $percent, $message)

    $label.Text = $message
    $parsedPercent = -1
    if ([int]::TryParse($percent, [ref]$parsedPercent) -and $parsedPercent -ge 0) {{
        if ($progress.Style -ne 'Continuous') {{
            $progress.Style = 'Continuous'
        }}
        $value = [Math]::Max(0, [Math]::Min(100, $parsedPercent))
        $progress.Value = $value
    }}
    else {{
        if ($progress.Style -ne 'Marquee') {{
            $progress.Style = 'Marquee'
        }}
    }}

    if ($state -eq 'done') {{
        $progress.Style = 'Continuous'
        $progress.Value = 100
        if (-not $script:doneTimer) {{
            $script:doneTimer = New-Object System.Windows.Forms.Timer
            $script:doneTimer.Interval = 1000
            $script:doneTimer.Add_Tick({{
                $script:doneTimer.Stop()
                $form.Close()
            }})
            $script:doneTimer.Start()
        }}
    }}
    elseif ($state -eq 'error') {{
        $progress.Style = 'Continuous'
        $progress.Value = 0
    }}
}}

$timer = New-Object System.Windows.Forms.Timer
$timer.Interval = 400
$timer.Add_Tick({{
    if (-not (Test-Path $StatusPath)) {{
        $timer.Stop()
        $form.Close()
        return
    }}
    $line = (Get-Content $StatusPath -ErrorAction SilentlyContinue | Select-Object -Last 1)
    if (-not $line) {{ return }}
    $parts = $line.Split('|',3)
    if ($parts.Length -lt 3) {{ return }}
    Set-Status $parts[0] $parts[1] $parts[2]
}})

$timer.Start()
$form.Add_FormClosing({{
    $timer.Stop()
    if ($script:doneTimer) {{ $script:doneTimer.Stop() }}
}})
[System.Windows.Forms.Application]::Run($form)
""")

                            with open(progress_helper_ps_path, 'w', encoding='utf-8-sig') as helper_file:
                                helper_file.write(progress_helper_template.format(
                                    status_path=status_path_ps.replace("'", "''"),
                                    window_title=helper_title_ps.replace("'", "''"),
                                    initial_message=helper_message_ps.replace("'", "''"),
                                ))

                            helper_cmd = ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', progress_helper_ps_path]
                            creation_flags = getattr(subprocess, 'CREATE_NEW_CONSOLE', 0)
                            progress_helper_proc = subprocess.Popen(helper_cmd, creationflags=creation_flags)
                    except Exception as helper_err:
                        print(f"Failed to start progress helper: {helper_err}")

                    if sys.platform == "win32":
                        app_executable_name = "Chord-to-MIDI-GENERATOR.exe"
                        staging_root = Path(target_dir) / f"staging_{latest_version_str}"
                        if staging_root.exists():
                            shutil.rmtree(staging_root)
                        staging_root.mkdir(parents=True, exist_ok=True)

                        with tarfile.open(final_path, "r:gz") as tar:
                            tar.extractall(path=staging_root)

                        arch_suffix = "win-x86"
                        platform_archives = list(staging_root.rglob(f"*-{arch_suffix}.zip"))
                        if not platform_archives:
                            raise FileNotFoundError(
                                f"Could not find Windows archive matching '*-{arch_suffix}.zip' in {staging_root}"
                            )
                        platform_archive_path = platform_archives[0]

                        platform_extract_dir = staging_root / "new_build"
                        if platform_extract_dir.exists():
                            shutil.rmtree(platform_extract_dir)
                        shutil.unpack_archive(str(platform_archive_path), str(platform_extract_dir))

                        new_app_root = platform_extract_dir / app_install_dir.name
                        if not new_app_root.exists():
                            candidate_dirs = [p for p in platform_extract_dir.iterdir() if p.is_dir()]
                            if len(candidate_dirs) == 1:
                                new_app_root = candidate_dirs[0]
                            else:
                                raise FileNotFoundError(
                                    f"Could not locate extracted app directory inside {platform_extract_dir}"
                                )

                        app_dir_str = str(app_install_dir)
                        old_dir_str = app_dir_str + ".old"
                        staging_root_str = str(staging_root)
                        new_app_root_str = str(new_app_root)

                        current_pid = os.getpid()
                        script_path = os.path.join(writable_dir, '_updater_win.bat')
                        script_content = textwrap.dedent(f"""\
                            @echo off
                            setlocal enableextensions enabledelayedexpansion
                            chcp 65001 >nul

                            set "APP_DIR={app_dir_str}"
                            set "OLD_APP_DIR={old_dir_str}"
                            set "STAGING_DIR={staging_root_str}"
                            set "NEW_APP_DIR={new_app_root_str}"
                            set "LOG_FILE={updater_log_path}"
                            set "FINAL_ARCHIVE={final_path}"
                            set "PARENT_PID={current_pid}"
                            set "STATUS_FILE={status_file_path}"
                            set "UPDATE_FLAG={update_flag_path}"

                            fsutil dirty query %SYSTEMDRIVE% >nul 2>&1
                            if errorlevel 1 (
                                call :update_status waiting 8 "관리자 권한을 요청 중입니다... (Requesting administrator approval...)"
                                powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath 'cmd.exe' -ArgumentList '/c','\"%~f0\"' -Verb RunAs"
                                exit /b
                            )

                            call :update_status preparing -1 "설치 준비 중... (Preparing installer...)"
                            echo [%date% %time%] Starting Windows updater > "%LOG_FILE%"
                            timeout /t 2 /nobreak >nul

                            call :update_status waiting 12 "실행 중인 앱 종료 대기 중... (Waiting for app to close...)"
                            call :wait_for_parent
                            if errorlevel 1 goto restore

                            call :ensure_other_instances
                            if errorlevel 1 goto restore

                            if exist "%OLD_APP_DIR%" (
                                rmdir /s /q "%OLD_APP_DIR%" >> "%LOG_FILE%" 2>&1
                            )

                            call :update_status installing 60 "기존 버전을 백업 중... (Backing up current version...)"
                            robocopy "%APP_DIR%" "%OLD_APP_DIR%" /MIR /COPYALL /R:2 /W:1 /NFL /NDL /NJH /NJS >> "%LOG_FILE%" 2>&1
                            set "RC=%ERRORLEVEL%"
                            if %RC% GEQ 8 goto restore

                            call :update_status installing 75 "새 파일을 복사 중... (Copying new files...)"
                            robocopy "%NEW_APP_DIR%" "%APP_DIR%" /MIR /COPYALL /R:2 /W:1 /NFL /NDL /NJH /NJS >> "%LOG_FILE%" 2>&1
                            set "RC=%ERRORLEVEL%"
                            if %RC% GEQ 8 goto restore

                            call :update_status installing 82 "권한 및 설정 정리 중... (Finalising files...)"

                            call :update_status restarting 95 "새 버전을 실행 중... (Launching new version...)"
                            start "" "%APP_DIR%\\{app_executable_name}"
                            timeout /t 5 /nobreak >nul

                            call :update_status cleaning 92 "임시 파일 정리 중... (Cleaning temporary files...)"
                            if exist "%FINAL_ARCHIVE%" del "%FINAL_ARCHIVE%" >> "%LOG_FILE%" 2>&1
                            if exist "%OLD_APP_DIR%" rmdir /s /q "%OLD_APP_DIR%" >> "%LOG_FILE%" 2>&1
                            if exist "%STAGING_DIR%" rmdir /s /q "%STAGING_DIR%" >> "%LOG_FILE%" 2>&1

                            call :update_status done 100 "업데이트 완료! (Update complete!)"
                            if exist "%UPDATE_FLAG%" del "%UPDATE_FLAG%" >nul 2>&1
                            timeout /t 1 /nobreak >nul
                            if exist "%STATUS_FILE%" del "%STATUS_FILE%" >nul 2>&1

                            del "%~f0"
                            exit /b 0

:wait_for_parent
                            echo [%date% %time%] Waiting for process %PARENT_PID% to exit >> "%LOG_FILE%"
                            for /L %%i in (1,1,60) do (
                                tasklist /FI "PID eq %PARENT_PID%" | findstr /I "%PARENT_PID%" >nul
                                if errorlevel 1 goto wait_parent_success
                                timeout /t 1 /nobreak >nul
                            )
                            echo [%date% %time%] Timed out waiting for process %PARENT_PID% to exit. >> "%LOG_FILE%"
                            call :update_status error 0 "앱 종료 대기 중 타임아웃 발생 (Timed out waiting for app to close)"
                            exit /b 1

:wait_parent_success
                            echo [%date% %time%] Process %PARENT_PID% has exited. >> "%LOG_FILE%"
                            exit /b 0

:restore
                            echo [%date% %time%] Update failed, attempting restore >> "%LOG_FILE%"
                            call :update_status error 0 "업데이트 실패: 자세한 내용은 로그를 확인하세요. (Update failed; see log.)"
                            if exist "%OLD_APP_DIR%" (
                                robocopy "%OLD_APP_DIR%" "%APP_DIR%" /MIR /COPYALL /R:2 /W:1 /NFL /NDL /NJH /NJS >> "%LOG_FILE%" 2>&1
                            )
                            if exist "%UPDATE_FLAG%" del "%UPDATE_FLAG%" >nul 2>&1
                            exit /b 1

:ensure_other_instances
                            set "_RETRY=0"
:check_instances
                            tasklist /FI "IMAGENAME eq {app_executable_name}" | find /I "{app_executable_name}" >nul
                            if errorlevel 1 goto instances_clear
                            if !_RETRY! GEQ 20 goto instances_fail
                            call :update_status waiting 18 "다른 실행 인스턴스 종료 대기 중... (Waiting for other instances to close...)"
                            timeout /t 1 /nobreak >nul
                            set /a _RETRY+=1
                            goto check_instances
:instances_fail
                            call :update_status error 0 "다른 실행 인스턴스가 종료되지 않았습니다. (Another instance is still running.)"
                            exit /b 1
:instances_clear
                            exit /b 0

:update_status
                            setlocal enableextensions enabledelayedexpansion
                            set "STATE=%~1"
                            set "PERCENT=%~2"
                            set "MESSAGE=%~3"
                            set "STATE=!STATE!"
                            set "PERCENT=!PERCENT!"
                            set "MESSAGE=!MESSAGE!"
                            powershell -NoProfile -Command "$line = $env:STATE + '|' + $env:PERCENT + '|' + $env:MESSAGE; Set-Content -Path $env:STATUS_FILE -Value $line -Encoding UTF8" >nul 2>&1
                            endlocal
                            exit /b 0
                        """)

                        with open(script_path, 'w', encoding='utf-8') as f:
                            f.write(script_content)

                        progress_window.update_status("설치 스크립트를 실행합니다...", None)
                        CREATE_NO_WINDOW = 0x08000000
                        subprocess.Popen(
                            ["cmd.exe", "/c", script_path],
                            creationflags=CREATE_NO_WINDOW,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                        update_script_started = True

                    else:
                        current_app_path = str(app_install_dir)

                        if sys.platform == "darwin":
                            try:
                                subprocess.run(
                                    ["xattr", "-dr", "com.apple.quarantine", current_app_path],
                                    check=False,
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL,
                                )
                            except Exception as attr_err:
                                print(f"Warning: failed to clear quarantine attribute: {attr_err}")

                            app_executable_name = "Chord-to-MIDI-GENERATOR"
                            restart_cmd = f"open '{os.path.join(app_install_dir.parent, app_executable_name + '.app')}'"
                        else:
                            app_executable_name = "Chord-to-MIDI-GENERATOR"
                            executable_path = os.path.join(app_install_dir.parent, app_executable_name)
                            restart_cmd = f"'{executable_path}'"

                        extract_to_dir = app_install_dir.parent
                        if sys.platform == "darwin":
                            extract_str = str(extract_to_dir)
                            if "AppTranslocation" in extract_str or not os.access(extract_str, os.W_OK):
                                if progress_window:
                                    progress_window.close()
                                    progress_window = None
                                title = "자동 업데이트 불가 (Update Blocked)"
                                message = (
                                    "현재 애플리케이션이 읽기 전용 위치에서 실행되고 있어 자동 업데이트를 수행할 수 없습니다.\n"
                                    "앱을 '응용 프로그램' 폴더 등 쓰기 가능한 위치로 이동한 뒤 다시 실행해 주세요."
                                )
                                messagebox.showerror(title, message)
                                raise RuntimeError("macOS auto-update blocked due to read-only App Translocation location")

                        staging_root = Path(target_dir) / f"staging_{latest_version_str}_{sys.platform}"
                        if staging_root.exists():
                            shutil.rmtree(staging_root)
                        staging_root.mkdir(parents=True, exist_ok=True)
                        staging_root_str = str(staging_root)

                        if progress_window:
                            progress_window.update_status("설치 스크립트를 준비 중...", None)

                        escaped_current_app = _escape_for_py(current_app_path)
                        escaped_archive_path = _escape_for_py(final_path)
                        escaped_restart_cmd = _escape_for_py(restart_cmd)
                        escaped_app_name = _escape_for_py(app_executable_name)
                        escaped_staging_dir = _escape_for_py(staging_root_str)
                        escaped_status_path = _escape_for_py(status_file_path)
                        escaped_update_flag = _escape_for_py(str(update_flag_path))
                        parent_pid = os.getpid()

                        updater_script_template = textwrap.dedent("""\
import os
import sys
import time
import shutil
import subprocess
import platform
import glob
import stat
import errno

current_app_path = r"{current_app_path}"
old_app_path = current_app_path + '.old'
archive_path = r"{archive_path}"
restart_cmd_str = r"{restart_cmd}"
app_executable_name = r"{app_executable_name}"
staging_dir = r"{staging_dir}"
parent_pid = {parent_pid}
status_path = r"{status_path}"
update_flag_path = r"{update_flag_path}"

encountered_error = False


def ensure_clean_dir(path):
    if os.path.exists(path):
        shutil.rmtree(path, ignore_errors=True)
    os.makedirs(path, exist_ok=True)


def loosen_path(path):
    if not os.path.exists(path):
        return
    stack = []
    if os.path.isdir(path) and not os.path.islink(path):
        for root, dirs, files in os.walk(path):
            for name in files:
                stack.append(os.path.join(root, name))
            for name in dirs:
                stack.append(os.path.join(root, name))
    stack.append(path)
    for item in stack:
        try:
            os.chmod(item, stat.S_IRWXU)
        except OSError:
            pass
        if hasattr(os, "chflags"):
            try:
                os.chflags(item, 0)
            except OSError:
                pass


def remove_path(path):
    if not os.path.exists(path):
        return

    def _onerror(func, p, exc_info):
        loosen_path(p)
        func(p)

    loosen_path(path)
    removed = False
    if os.path.isdir(path) and not os.path.islink(path):
        try:
            shutil.rmtree(path, onerror=_onerror)
            removed = True
        except OSError:
            removed = False
    else:
        try:
            os.remove(path)
            removed = True
        except (IsADirectoryError, OSError):
            try:
                shutil.rmtree(path, onerror=_onerror)
                removed = True
            except OSError:
                removed = False

    if not removed:
        rm_cmd = shutil.which("rm")
        if rm_cmd:
            subprocess.run([rm_cmd, "-rf", path], check=False)
        if os.path.exists(path):
            raise OSError(f"Failed to remove path: {{path}}")


def move_to_backup(src, backup):
    if not os.path.exists(src):
        return
    remove_path(backup)
    loosen_path(src)
    try:
        os.replace(src, backup)
    except OSError as err:
        print(f"Rename failed ({{err}}), attempting copy fallback.")
        remove_path(backup)
        shutil.copytree(src, backup, copy_function=shutil.copy2)
        remove_path(src)


def is_permission_error(err):
    if isinstance(err, PermissionError):
        return True
    if isinstance(err, OSError) and getattr(err, "errno", None) in (errno.EPERM, errno.EACCES):
        return True
    msg = str(err).lower()
    return "operation not permitted" in msg or "permission denied" in msg


def replace_app_via_finder(source_app: str, target_app: str) -> None:
    parent_dir = os.path.dirname(target_app.rstrip(os.sep))
    if not parent_dir:
        raise RuntimeError("Unable to determine destination directory for Finder replacement.")

    def _esc(value: str) -> str:
        return value.replace("\\\\", "\\\\\\\\").replace('"', '\\"')

    source_esc = _esc(source_app)
    target_esc = _esc(target_app)
    parent_esc = _esc(parent_dir)
    app_name = _esc(os.path.basename(target_app.rstrip(os.sep)))

    cmd = [
        "osascript",
        "-e", "set sourcePath to POSIX file \"" + source_esc + "\"",
        "-e", "set destPathString to \"" + target_esc + "\"",
        "-e", "set destParent to POSIX file \"" + parent_esc + "\" as alias",
        "-e", 'set destExists to false',
        "-e", 'set destRef to missing value',
        "-e", 'try',
        "-e", '    set destRef to POSIX file destPathString',
        "-e", '    set destExists to true',
        "-e", 'on error',
        "-e", '    set destRef to missing value',
        "-e", 'end try',
        "-e", 'tell application "Finder"',
        "-e", '    with timeout of 600 seconds',
        "-e", '        if destExists then delete destRef',
        "-e", '        set duplicatedItem to duplicate sourcePath to destParent',
        "-e", '        set name of duplicatedItem to "' + app_name + '"',
        "-e", '    end timeout',
        "-e", 'end tell'
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        details = (result.stderr or result.stdout or '').strip()
        raise RuntimeError("Finder replacement failed: " + details)


def write_status(state: str, message: str, percent=None) -> None:
    if not status_path:
        return
    try:
        percent_value = -1 if percent is None else int(percent)
    except (TypeError, ValueError):
        percent_value = -1

    safe_message = str(message).replace('\\n', ' ').replace('|', '/')
    tmp_path = status_path + '.tmp'
    try:
        with open(tmp_path, 'w', encoding='utf-8') as status_file:
            status_file.write(state + '|' + str(percent_value) + '|' + safe_message)
        os.replace(tmp_path, status_path)
    except OSError:
        pass


def is_process_running(pid: int) -> bool:
    try:
        if pid <= 0:
            return False
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def wait_for_parent_exit(pid: int, timeout: float = 90.0) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        if not is_process_running(pid):
            return True
        time.sleep(0.5)
    return not is_process_running(pid)


try:
    write_status('waiting', '앱 종료 대기 중... (Waiting for the app to close...)', 10)
    # Small initial delay and then ensure parent fully exited
    time.sleep(1.5)
    if parent_pid:
        print(f"Waiting for parent process {parent_pid} to exit...")
        if not wait_for_parent_exit(parent_pid, timeout=90.0):
            print(f"Parent process {parent_pid} still running after timeout; proceeding anyway.")

    write_status('extracting', '압축 파일 해제 준비 중... (Preparing extraction...)', 25)

    ensure_clean_dir(staging_dir)
    primary_extract_dir = os.path.join(staging_dir, 'primary')
    ensure_clean_dir(primary_extract_dir)

    print(f'Extracting primary archive {{archive_path}} into {{primary_extract_dir}}...')
    write_status('extracting', '압축 파일 해제 중... (Extracting package...)', 40)
    if archive_path.endswith('.tar.gz'):
        tar_cmd = f"tar -xzf '{{archive_path}}' -C '{{primary_extract_dir}}'"
        subprocess.run(tar_cmd, shell=True, check=True)
    else:
        shutil.unpack_archive(archive_path, primary_extract_dir)

    print("Searching for platform-specific archive recursively...")
    arch_suffix = ""
    if sys.platform == "darwin":
        arch_suffix = "mac-arm64" if platform.machine() == "arm64" else "mac-x86_64"
    elif sys.platform.startswith("linux"):
        arch_suffix = "linux-x86_64"

    if not arch_suffix:
        raise RuntimeError(f"Unsupported platform: {{sys.platform}}")

    zip_pattern = os.path.join(primary_extract_dir, '**', f'*-{{arch_suffix}}.zip')
    found_archives = glob.glob(zip_pattern, recursive=True)
    if not found_archives:
        raise FileNotFoundError(f"Could not find platform archive with pattern: {{zip_pattern}}")

    platform_archive_path = found_archives[0]
    print(f"Found platform archive: {{platform_archive_path}}")

    platform_extract_dir = os.path.join(staging_dir, 'payload')
    ensure_clean_dir(platform_extract_dir)

    print("Unpacking platform archive...")
    if sys.platform == "darwin":
        ditto_cmd = f"ditto -xk '{{platform_archive_path}}' '{{platform_extract_dir}}'"
        subprocess.run(ditto_cmd, shell=True, check=True)
    else:
        shutil.unpack_archive(platform_archive_path, platform_extract_dir)

    write_status('installing', '새 파일 배치 중... (Deploying new version...)', 60)

    if sys.platform == "darwin":
        candidate_apps = glob.glob(os.path.join(platform_extract_dir, '*.app'))
        if not candidate_apps:
            candidate_apps = glob.glob(os.path.join(platform_extract_dir, '**', '*.app'), recursive=True)
        if not candidate_apps:
            raise FileNotFoundError("Could not find .app bundle in extracted payload.")
        new_app_root = candidate_apps[0]
    else:
        expected_name = os.path.basename(current_app_path.rstrip(os.sep))
        candidate_path = os.path.join(platform_extract_dir, expected_name)
        if os.path.exists(candidate_path):
            new_app_root = candidate_path
        else:
            candidates = [p for p in glob.glob(os.path.join(platform_extract_dir, '*')) if os.path.isdir(p)]
            if len(candidates) == 1:
                new_app_root = candidates[0]
            else:
                raise FileNotFoundError("Could not locate application directory in extracted payload.")

    use_finder_replace = False

    try:
        write_status('installing', '기존 버전을 백업 중... (Backing up current version...)', 65)
        print(f'Moving {{current_app_path}} to {{old_app_path}}')
        move_to_backup(current_app_path, old_app_path)

        write_status('installing', '새 파일을 배치 중... (Placing new build...)', 75)
        print(f'Placing new build from {{new_app_root}} into {{current_app_path}}')
        remove_path(current_app_path)
        shutil.move(new_app_root, current_app_path)
    except Exception as replace_err:
        if sys.platform == "darwin" and is_permission_error(replace_err):
            print("Permission issue encountered (" + str(replace_err) + "); attempting Finder-assisted replacement.")
            write_status('installing', 'Finder를 통해 교체 중... (Replacing via Finder...)', 75)
            use_finder_replace = True
        else:
            raise

    if use_finder_replace:
        replace_app_via_finder(new_app_root, current_app_path)
        write_status('installing', '새 파일을 배치 중... (Placing new build...)', 78)
        # Attempt to clean up any backup created during fallback; ignore failures.
        if os.path.exists(old_app_path):
            try:
                remove_path(old_app_path)
            except Exception:
                pass

    if sys.platform == "darwin":
        write_status('installing', '실행 권한을 정리 중... (Adjusting permissions...)', 82)
        subprocess.run(f"xattr -dr com.apple.quarantine '{{current_app_path}}'", shell=True, check=False)
        executable_path = os.path.join(current_app_path, 'Contents', 'MacOS', app_executable_name)
        if os.path.exists(executable_path):
            chmod_cmd = f"chmod +x '{{executable_path}}'"
            subprocess.run(chmod_cmd, shell=True, check=False)

    write_status('restarting', '새 버전을 실행 중... (Launching new version...)', 95)
    print('Restarting application...')
    subprocess.Popen(restart_cmd_str, shell=True)

    print("Cleaning up staging area...")
    shutil.rmtree(staging_dir, ignore_errors=True)

    write_status('cleaning', '임시 파일 정리 중... (Cleaning up temporary files...)', 92)

    time.sleep(5)
    if os.path.exists(old_app_path):
        print(f'Cleaning up {{old_app_path}}')
        remove_path(old_app_path)

    write_status('done', '업데이트 완료! (Update complete!)', 100)

except Exception as e:
    encountered_error = True
    write_status('error', f'업데이트 실패: {{e}}', 0)
    print(f'Update script failed: {{e}}')
    if os.path.exists(old_app_path) and not os.path.exists(current_app_path):
        try:
            remove_path(current_app_path)
            os.replace(old_app_path, current_app_path)
        except Exception as e_restore:
            print(f"Failed to restore old version: {{e_restore}}")

finally:
    if not encountered_error:
        try:
            time.sleep(1.0)
        except Exception:
            pass

    if status_path and os.path.exists(status_path) and not encountered_error:
        try:
            os.remove(status_path)
        except OSError:
            pass

    if update_flag_path and os.path.exists(update_flag_path):
        try:
            os.remove(update_flag_path)
        except OSError:
            pass

    if os.path.exists(archive_path):
        os.remove(archive_path)
    if os.path.exists(staging_dir):
        remove_path(staging_dir)
    try:
        os.remove(__file__)
    except OSError:
        pass
""")

                        updater_script_content = updater_script_template.format(
                            current_app_path=escaped_current_app,
                            archive_path=escaped_archive_path,
                            restart_cmd=escaped_restart_cmd,
                            app_executable_name=escaped_app_name,
                            staging_dir=escaped_staging_dir,
                            parent_pid=parent_pid,
                            status_path=escaped_status_path,
                            update_flag_path=escaped_update_flag,
                        )

                        script_path = os.path.join(writable_dir, '_updater.py')
                        with open(script_path, 'w', encoding='utf-8') as f:
                            f.write(updater_script_content)

                        if sys.platform == "darwin":
                            target_parent = os.path.dirname(current_app_path.rstrip(os.sep)) or os.path.dirname(current_app_path)
                            can_write_parent = os.access(target_parent, os.W_OK)
                            can_write_app = os.access(current_app_path, os.W_OK)
                            needs_admin = not (can_write_parent and can_write_app)

                            python_executable = "/usr/bin/python3"

                            if needs_admin:
                                command_with_redirect = f"'{python_executable}' '{script_path}' > '{updater_log_path}' 2>&1"
                                escaped_cmd = command_with_redirect.replace("\\", "\\\\").replace('"', '\\"')
                                applescript = f'do shell script "{escaped_cmd}" with administrator privileges'
                                subprocess.Popen(['osascript', '-e', applescript])
                            else:
                                with open(updater_log_path, 'w', encoding='utf-8') as log_file:
                                    subprocess.Popen([python_executable, script_path], stdout=log_file, stderr=log_file)
                            update_script_started = True
                        else:
                            py = sys.executable or "python3"
                            with open(updater_log_path, 'w', encoding='utf-8') as log_file:
                                subprocess.Popen([py, script_path], stdout=log_file, stderr=log_file)
                            update_script_started = True
                    
                    # 메인 애플리케이션 종료
                    sys.exit(0)

                except Exception as e:
                    if tmp_path and os.path.exists(tmp_path):
                        try:
                            os.remove(tmp_path)
                        except OSError as e_clean:
                            print(f"Error cleaning up temp file: {e_clean}")
                    if progress_window:
                        progress_window.update_status("업데이트 실패", None)
                        progress_window.close()
                        progress_window = None

                    title = "업데이트 오류 (Update Error)"
                    message = (
                        f"업데이트 다운로드 또는 확인에 실패했습니다.\n"
                        f"---\n"
                        f"Failed to download or verify the update.\n\n"
                        f"Error: {e}"
                    )
                    messagebox.showerror(title, message)
                    print(f"Error during manual update process: {e}")
                    raise
                finally:
                    if progress_window:
                        progress_window.close()
                    if progress_helper_proc and not update_script_started:
                        try:
                            progress_helper_proc.terminate()
                        except Exception:
                            pass
                    if not update_script_started:
                        if status_file_path and os.path.exists(status_file_path):
                            try:
                                os.remove(status_file_path)
                            except OSError:
                                pass
                        if update_flag_path.exists():
                            try:
                                update_flag_path.unlink()
                            except OSError:
                                pass

    except Exception as e:
        # ---------------- TUF 업데이트 실패 시 '플랜 B' 실행 ----------------
        import traceback
        print("--- DETAILED UPDATE ERROR ---")
        traceback.print_exc()
        print("-----------------------------")
        print(f"TUF update check failed: {e}")
        print("Executing fallback: Opening the releases page directly.")
        
        try:
            # GitHub API 호출 대신, 항상 최신 릴리즈로 연결되는 URL을 직접 사용합니다.
            # 이것이 훨씬 안정적이며, 문제가 발생한 requests 라이브러리 호출을 피할 수 있습니다.
            latest_release_url = "https://github.com/kimtopseong/Chord-to-MIDI-GENERATOR/releases/latest"
            
            # 사용자에게 수동 업데이트 안내
            title = "수동 업데이트 필요 (Manual Update Required)"
            message = (
                f"새로운 버전을 확인하는 중 오류가 발생했습니다.\n"
                f"다운로드 페이지로 이동하여 최신 버전을 직접 확인하시겠습니까?\n"
                f"---\n"
                f"An error occurred while checking for a new version.\n"
                f"Would you like to go to the download page to check for the latest version manually?"
            )
            if messagebox.askyesno(title, message):
                webbrowser.open(latest_release_url)
        
        except Exception as fallback_error:
            # webbrowser.open 실패 등 최후의 예외 처리
            print(f"An unexpected error occurred during the fallback process: {fallback_error}")
    
    
    splash_root = tk.Tk(); splash_root.overrideredirect(True)
    try:
        image_path = App.resource_path("loading.png")
        splash_image = PhotoImage(file=image_path); width, height = splash_image.width(), splash_image.height()
        sw, sh = splash_root.winfo_screenwidth(), splash_root.winfo_screenheight()
        x, y = (sw // 2) - (width // 2), (sh // 2) - (height // 2)
        splash_root.geometry(f'{width}x{height}+{x}+{y}')
        tk.Label(splash_root, image=splash_image, bd=0).pack()
    except Exception as e:
        print(f"Splash image not found ('{e}'), using text fallback.")
        width, height = 400, 200; sw, sh = splash_root.winfo_screenwidth(), splash_root.winfo_screenheight()
        x, y = (sw // 2) - (width // 2), (sh // 2) - (height // 2)
        splash_root.geometry(f'{width}x{height}+{x}+{y}')
        tk.Label(splash_root, text="Loading Chord to MIDI Generator...", font=("Helvetica", 16)).pack(expand=True)
    splash_root.update()
    app = App(splash_root=splash_root)
    app.mainloop()
