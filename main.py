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
from typing import List, Optional
import os
import platform

import tkinter as tk
from tkinter import PhotoImage, filedialog, messagebox
import tkinter.ttk as ttk
import customtkinter as ctk
from mido import Message, MidiFile, MidiTrack, MetaMessage, bpm2tempo

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

APP_TITLE = "Chord-to-MIDI-GENERATOR"
LOGFILE = "chord_to_midi.log"
CURRENT_VERSION = "1.1.113"

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
        self.canvas.grid(row=0, column=0, sticky="nsew"); self.vsb.grid(row=0, column=1, sticky="ns")
        self.inner.bind("<Configure>", self._on_inner_configure); self.canvas.bind("<Configure>", self._on_canvas_configure)
    def _on_inner_configure(self, event): self.canvas.configure(scrollregion=self.canvas.bbox("all"))
    def _on_canvas_configure(self, event): self.canvas.itemconfig(self.inner_id, width=event.width)


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

        self.status_var = tk.StringVar(value="준비 중...")
        status_label = tk.Label(self.window, textvariable=self.status_var, font=("Helvetica", 12))
        status_label.pack(pady=(20, 10))

        self.progress = ttk.Progressbar(self.window, orient="horizontal", mode="determinate", length=280)
        self.progress.pack(pady=5)
        self.progress['maximum'] = 100
        self._progress_mode = "determinate"

        self.percent_var = tk.StringVar(value="0%")
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
        if self._created_root:
            tk._default_root = None


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
    KEYS = ['C','G','D','A','E','B','F#','C#','F','Bb','Eb','Ab','Db','Gb','Cb']
    KEY_PREFERS_SHARPS = {'C':True,'G':True,'D':True,'A':True,'E':True,'B':True,'F#':True,'C#':True, 'F':False,'Bb':False,'Eb':False,'Ab':False,'Db':False,'Gb':False,'Cb':False}
    MAJOR_DEGREE_TO_SEMITONES = {'I':0, 'II':2, 'III':4, 'IV':5, 'V':7, 'VI':9, 'VII':11}
    TENSIONS_LIST = ['b9', '9', '#9', '11', '#11', 'b13', '13']
    # [REQUEST] Reorder list and add 'blk'
    QUALITY_SYMBOLS = ["Major", "Minor", "7", "M7", "m7", "7b5", "M7b5", "m7b5", "dim", "dim7", "aug", "blk", "sus2", "sus4", "omit3", "omit5"]
    ROMAN_DEGREES_BUILDER = ['I', 'bII', 'II', 'bIII', 'III', 'IV', '#IV', 'V', 'bVI', 'VI', 'bVII', 'VII']

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
        s = text.strip()
        if not s: return App.ParsedChord(root='C', quality='Major')

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

        s = s.replace('maj7', 'M7').replace('Maj7','M7').replace('min','m').replace('-', 'm').replace('ø', 'm7b5').replace('°', 'dim')

        m_roman = re.match(fr'(?i)^([b#]?{App.ROMAN_PATTERN})', s)
        if m_roman:
            head = m_roman.group(1); is_roman_flag = True; rest = s[len(head):].strip()
            root = App.pc_to_name(App.roman_to_pc_offset(key, head), App.prefers_sharps(key))
        else:
            m_alpha = re.match(r'(?i)^([A-G][#b]?)', s)
            if m_alpha:
                head = m_alpha.group(1); is_roman_flag = False; rest = s[len(head):].strip()
                root = head[0].upper() + head[1:]
            else: return App.ParsedChord(root='C', quality='Major')

        quality, seventh, tensions, alterations = 'Major', None, [], []
        rest_mut = rest

        if '13' in rest_mut: tensions.append('13'); rest_mut = rest_mut.replace('13', '')
        if '11' in rest_mut: tensions.append('11'); rest_mut = rest_mut.replace('11', '')
        if '9' in rest_mut: tensions.append('9'); rest_mut = rest_mut.replace('9', '')
        
        sev_m = re.search(r'M7|m7|7|dim7', rest_mut)
        if sev_m:
            sev_str = sev_m.group(0)
            seventh = 'm7' if sev_str == '7' else sev_str
            rest_mut = rest_mut.replace(sev_str, '')
            if sev_str == 'm7': quality = 'Minor'
            elif sev_str == 'dim7': quality = 'dim'
        elif tensions or paren_contents:
            is_minor_in_parens = any('m' in p for p in paren_contents)
            if not is_minor_in_parens: seventh = 'm7'

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

        highest_tension_num = 0
        if p.tensions:
            highest_tension_num = max([int(re.sub(r'[^0-9]','',t)) for t in p.tensions])

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
            qual_str, sev_prefix, num_part, alt_str = '', 'm', '7b5', ''
        else:
            alt_str = ''.join(p.alterations)

        paren_str = f"({','.join(p.paren_contents)})" if p.paren_contents else ''
        om_str = ''.join([f"omit{o}" for o in p.omissions])
        bass_str = f"/{p.bass_note}" if p.bass_note and p.bass_note != p.root else ""

        return f"{base}{qual_str}{sev_prefix}{num_part}{alt_str}{om_str}{paren_str}{bass_str}"

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

            tension_map = {'9':14, 'b9':13, '#9':15, '11':17, '#11':18, '13':21, 'b13':20}
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
        if n <= 0: return []
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
                "alphabet": "알파벳",
                "degree": "도수",
                "omit5": "5음 생략",
                "omit_bass": "베이스 중복음 생략",
                "measures": "마디",
                "generate_midi": "MIDI 생성",
                "clear_all": "모두 지우기",
                "builder_title": "코드 빌더",
                "root": "근음",
                "quality": "종류",
                "tensions": "텐션",
                "reset_tensions": "텐션 초기화",
                "build_insert": "코드 만들고 넣기",
                "instructions_text": "입력한 코드를 MIDI로 변환해주는 도구입니다.\n\n"
                     "• 코드 구분은 공백만 사용됩니다. (예: C G/B Am7 F)\n"
                     "• 슬래시(/)는 베이스음을 지정합니다. (예: C/E는 C코드, 베이스 E)\n"
                     "• 코드의 전위(베이스 변경)는 로마자/알파벳 형식의 표기만 지원합니다. (예: IIIm/G)\n"
                     "• 코드와 도수(로마자) 간 변환이 가능합니다.\n\n"
                     "• omit3, omit5로 3음, 5음을 생략할 수 있습니다. (예: C7omit3)\n"
                     "• 5음 생략 버튼은 텐션과 5음이 반음 관계일 때 5음을 제거하는 기능입니다.\n"
                     "• '베이스 중복음 생략' 체크 시 코드와 베이스의 중복음을 제거합니다.\n"
                     "• 모든 코드는 한 옥타브 낮은 베이스음과 함께 연주됩니다.\n\n"
                     "• 코드 빌더는 선택한 마디 칸에 코드를 생성하는 도구입니다. 한 마디에는 최대 4개의 코드까지 입력할 수 있습니다.\n"
                     "• 마디 숫자를 입력하고 +, - 버튼을 누르면 원하는 만큼 마디를 추가하거나 제거할 수 있습니다.\n\n"
                     "• 문제가 발생할 경우 하단 Log 탭의 내용을 복사하여 개발자에게 제보 부탁드립니다.",
                "clear_confirm_title": "확인",
                "clear_confirm_message": "모든 마디에 입력된 코드를 정말로 지우시겠습니까?"
            },
            "en": {
                "title": "Chord to MIDI",
                "key": "Key",
                "alphabet": "Alphabet",
                "degree": "Degree",
                "omit5": "Omit 5th",
                "omit_bass": "Omit Dupe Bass",
                "measures": "Measures",
                "generate_midi": "Generate MIDI",
                "clear_all": "Clear All",
                "builder_title": "Chord Builder",
                "root": "Root",
                "quality": "Quality",
                "tensions": "Tensions",
                "reset_tensions": "Reset Tensions",
                "build_insert": "Build & Insert Chord",
                "instructions_text": "This tool converts entered chords into MIDI notes.\n\n"
                     "• Use spaces to separate chords (e.g., C G/B Am7 F)\n"
                     "• Use a slash (/) to specify a bass note (e.g., C/E means C chord with E bass)\n"
                     "• Inversions (changing bass notes) support only the Roman/Alphabet format (e.g., IIIm/G)\n"
                     "• Supports conversion between chord names and Roman numerals\n\n"
                     "• Use omit3, omit5 to omit the 3rd or 5th (e.g., C7omit3)\n"
                     "• The 'Omit 5th' option removes the 5th when it clashes with tensions\n"
                     "• Check 'Omit Duplicate Bass' to remove notes in the chord that match the bass\n"
                     "• All chords are played with a bass note one octave below\n\n"
                     "• The Chord Builder inserts chords into a selected measure. Up to 4 chords can be placed per measure\n"
                     "• Enter a number and press + or - to add or remove as many measures as you want\n\n"
                     "• If an error occurs, please copy the Log tab contents and report it to the developer.",
                "clear_confirm_title": "Confirmation",
                "clear_confirm_message": "Are you sure you want to clear all chords from all measures?"
            }
        }
        self.lang_code = "ko"
        self.geometry("1200x800"); self.minsize(1080, 720)
        font_family = "NanumGothic" if platform.system() == "Windows" else "Segoe UI"
        self.font_main = ctk.CTkFont(family=font_family, size=14); self.font_bold = ctk.CTkFont(family=font_family, size=14, weight="bold")
        self.font_large_bold = ctk.CTkFont(family=font_family, size=18, weight="bold"); self.font_measure = ctk.CTkFont(family="Menlo", size=12)
        self._suppress, self._building, self.last_focused_entry = True, False, None
        
        self.grid_columnconfigure(0, weight=1); self.grid_columnconfigure(1, minsize=320, weight=0); self.grid_rowconfigure(1, weight=1)
        
        self.settings = ctk.CTkFrame(self, fg_color="transparent"); self.settings.grid(row=0, column=0, columnspan=2, padx=10, pady=(10,5), sticky="ew")
        self.settings.grid_columnconfigure(1, weight=1)
        
        self.left_settings_group = ctk.CTkFrame(self.settings, fg_color="transparent"); self.left_settings_group.grid(row=0, column=0, padx=0, pady=5, sticky="w")
        
        self.lang_var = tk.StringVar(value="한국어")
        self.lang_toggle = ctk.CTkSegmentedButton(self.left_settings_group, values=["한국어", "English"], variable=self.lang_var, command=self._update_language); self.lang_toggle.pack(side="left")
        
        self.key_label = ctk.CTkLabel(self.left_settings_group, font=self.font_bold); self.key_label.pack(side="left", padx=(15, 8))
        self.key_var = tk.StringVar(value="C"); self.key_menu = ctk.CTkOptionMenu(self.left_settings_group, values=App.KEYS, variable=self.key_var, command=self._on_key_changed, width=100); self.key_menu.pack(side="left")
        self.mode_var = tk.StringVar(value=self.i18n[self.lang_code]["alphabet"])
        self.mode_btn = ctk.CTkSegmentedButton(self.left_settings_group, variable=self.mode_var, command=self._on_mode_changed); self.mode_btn.pack(side="left", padx=(10,0))
        
        self.right_settings_group = ctk.CTkFrame(self.settings, fg_color="transparent"); self.right_settings_group.grid(row=0, column=2, padx=0, pady=5, sticky="e")
        
        self.omit5_var = tk.BooleanVar(value=True); self.omit5_chk = ctk.CTkCheckBox(self.right_settings_group, variable=self.omit5_var, font=self.font_main); self.omit5_chk.pack(side="left", padx=(0,10))
        self.omit_bass_var = tk.BooleanVar(value=False); self.omit_bass_chk = ctk.CTkCheckBox(self.right_settings_group, variable=self.omit_bass_var, font=self.font_main); self.omit_bass_chk.pack(side="left", padx=(0,15))
        
        self.measures_label = ctk.CTkLabel(self.right_settings_group, font=self.font_bold); self.measures_label.pack(side="left", padx=(0,8))
        self.sub_4_btn = ctk.CTkButton(self.right_settings_group, text="-", width=30, font=self.font_main, command=self._decrease_measures); self.sub_4_btn.pack(side="left")
        self.measures_entry = ctk.CTkEntry(self.right_settings_group, width=45, font=self.font_main, justify="center"); self.measures_entry.insert(0, "4"); self.measures_entry.pack(side="left", padx=4)
        self.add_4_btn = ctk.CTkButton(self.right_settings_group, text="+", width=30, font=self.font_main, command=self._increase_measures); self.add_4_btn.pack(side="left", padx=(0,15))
        
        action_buttons_group = ctk.CTkFrame(self.right_settings_group, fg_color="transparent"); action_buttons_group.pack(side="left", padx=(0,0))
        self.clear_all_btn = ctk.CTkButton(action_buttons_group, font=self.font_main, command=self._clear_all_chords, fg_color="transparent", border_width=1); self.clear_all_btn.pack(side="left", padx=(0,10))
        self.gen_btn = ctk.CTkButton(action_buttons_group, font=self.font_bold, command=self._on_generate_midi); self.gen_btn.pack(side="left")
        
        self.main_area = ctk.CTkFrame(self, fg_color="transparent"); self.main_area.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
        self.main_area.grid_rowconfigure(0, weight=1); self.main_area.grid_columnconfigure(0, weight=1)
        self.scroll = ScrollableFrame(self.main_area); self.scroll.grid(row=0, column=0, sticky="nsew")
        self.measures_frame = self.scroll.inner
        
        self.builder_frame = ctk.CTkFrame(self); self.builder_frame.grid(row=1, column=1, padx=(0,10), pady=5, sticky="ns")
        self.builder_frame.grid_columnconfigure(0, weight=1)
        self.builder_title_label = ctk.CTkLabel(self.builder_frame, font=self.font_large_bold); self.builder_title_label.grid(row=0, column=0, columnspan=4, padx=15, pady=(15,10), sticky="w")
        
        ctk.CTkFrame(self.builder_frame, height=1, fg_color=ctk.ThemeManager.theme["CTkFrame"]["border_color"]).grid(row=1, column=0, padx=15, pady=5, sticky="ew")
        self.root_label = ctk.CTkLabel(self.builder_frame, font=self.font_bold); self.root_label.grid(row=2, column=0, columnspan=4, padx=15, pady=(10,2), sticky="w")
        self.builder_root_var = tk.StringVar(value="C"); self.builder_root_menu = ctk.CTkOptionMenu(self.builder_frame, values=App.NOTE_NAMES_SHARP, variable=self.builder_root_var, font=self.font_main, dropdown_font=self.font_main); self.builder_root_menu.grid(row=3, column=0, columnspan=4, padx=15, pady=0, sticky="ew")
        
        self.quality_label = ctk.CTkLabel(self.builder_frame, font=self.font_bold); self.quality_label.grid(row=4, column=0, columnspan=4, padx=15, pady=(10,2), sticky="w")
        self.builder_quality_var = tk.StringVar(value="Major"); self.builder_quality_menu = ctk.CTkOptionMenu(self.builder_frame, values=App.QUALITY_SYMBOLS, variable=self.builder_quality_var, font=self.font_main, dropdown_font=self.font_main); self.builder_quality_menu.grid(row=5, column=0, columnspan=4, padx=15, pady=0, sticky="ew")
        
        ctk.CTkFrame(self.builder_frame, height=1, fg_color=ctk.ThemeManager.theme["CTkFrame"]["border_color"]).grid(row=6, column=0, padx=15, pady=10, sticky="ew")
        
        self.tensions_label = ctk.CTkLabel(self.builder_frame, font=self.font_bold); self.tensions_label.grid(row=7, column=0, columnspan=4, padx=15, pady=(5,5), sticky="w")
        self.tension_button_frame = ctk.CTkFrame(self.builder_frame, fg_color="transparent"); self.tension_button_frame.grid(row=8, column=0, columnspan=4, padx=15, pady=0, sticky="ew")
        self.tension_vars = {}
        for i, tension in enumerate(App.TENSIONS_LIST):
            var = tk.BooleanVar(value=False); self.tension_vars[tension] = var
            chk = ctk.CTkCheckBox(self.tension_button_frame, text=tension, variable=var, font=self.font_main); chk.grid(row=i//4, column=i%4, padx=2, pady=2, sticky="w")
        
        self.reset_tensions_btn = ctk.CTkButton(self.builder_frame, font=self.font_main, command=self._reset_tensions, fg_color="transparent", border_width=1); self.reset_tensions_btn.grid(row=9, column=0, columnspan=4, padx=15, pady=(10,5), sticky="ew")
        self.insert_btn = ctk.CTkButton(self.builder_frame, font=self.font_bold, command=self._on_build_and_insert); self.insert_btn.grid(row=10, column=0, columnspan=4, padx=15, pady=5, sticky="ew")
        
        self.bottom_tabs = ctk.CTkTabview(self, height=140); self.bottom_tabs.grid(row=2, column=0, columnspan=2, padx=10, pady=(5,10), sticky="ew")
        self.bottom_tabs.add("Instructions"); self.bottom_tabs.add("Log")
        self.instructions = ctk.CTkTextbox(self.bottom_tabs.tab("Instructions"), font=self.font_main, wrap="word"); self.instructions.pack(expand=True, fill="both", padx=5, pady=5)
        self.log = ctk.CTkTextbox(self.bottom_tabs.tab("Log"), font=self.font_measure, wrap="none"); self.log.pack(expand=True, fill="both", padx=5, pady=5)
        
        self.context_menu = self._create_context_menu()
        self.total_measures = 16

        self.version_label = ctk.CTkLabel(self, text=f"v{CURRENT_VERSION}", font=ctk.CTkFont(size=12), text_color="gray50")
        self.version_label.grid(row=3, column=1, padx=10, pady=(0, 5), sticky="se")
        self.grid_rowconfigure(3, weight=0)

        # MIDI 생성 단축키 (Cmd+S / Ctrl+S) 바인딩
        def on_save_midi(event=None): self._on_generate_midi()
        if platform.system() == "Darwin":
            self.bind("<Command-s>", on_save_midi)
        else:
            self.bind("<Control-s>", on_save_midi)

        self._update_language(); self._suppress = False; self.after(50, self._rebuild_measures); self._log("App started.")
        self.after(100, self.splash_root.destroy)
        
    def _create_context_menu(self):
        menu = tk.Menu(self, tearoff=0); menu.add_command(label="Cut", command=lambda: self.focus_get().event_generate('<<Cut>>'))
        menu.add_command(label="Copy", command=lambda: self.focus_get().event_generate('<<Copy>>'))
        menu.add_command(label="Paste", command=lambda: self.focus_get().event_generate('<<Paste>>'))
        menu.add_separator(); menu.add_command(label="Select All", command=lambda: self.focus_get().event_generate('<<SelectAll>>'))
        return menu
    def _show_context_menu(self, event): self.context_menu.tk_popup(event.x_root, event.y_root)
    def _update_language(self, *_):
        self.lang_code = "en" if self.lang_var.get() == "English" else "ko"; lang = self.i18n[self.lang_code]
        is_alpha_mode = self.mode_var.get() in [self.i18n["ko"]["alphabet"], self.i18n["en"]["alphabet"]]
        self.title(lang["title"]); self.key_label.configure(text=lang["key"])
        self.mode_btn.configure(values=[lang["alphabet"], lang["degree"]]); self.mode_var.set(lang["alphabet"] if is_alpha_mode else lang["degree"])
        self.omit5_chk.configure(text=lang["omit5"]); self.omit_bass_chk.configure(text=lang["omit_bass"])
        self.measures_label.configure(text=lang["measures"]); self.gen_btn.configure(text=lang["generate_midi"])
        self.clear_all_btn.configure(text=lang["clear_all"])
        self.builder_title_label.configure(text=lang["builder_title"]); self.root_label.configure(text=lang["root"])
        self.quality_label.configure(text=lang["quality"]); self.tensions_label.configure(text=lang["tensions"])
        self.reset_tensions_btn.configure(text=lang["reset_tensions"]); self.insert_btn.configure(text=lang["build_insert"])
        self.instructions.configure(state="normal"); self.instructions.delete("1.0", "end")
        self.instructions.insert("1.0", lang["instructions_text"]); self.instructions.configure(state="disabled")
        self._update_builder_roots()
    def _update_builder_roots(self):
        is_degree_mode = self.mode_var.get() == self.i18n[self.lang_code]["degree"]
        if is_degree_mode:
            self.builder_root_menu.configure(values=App.roman_degrees_for_key(self.key_var.get())); self.builder_root_var.set('I')
        else:
            use_sharps = App.prefers_sharps(self.key_var.get())
            self.builder_root_menu.configure(values=App.NOTE_NAMES_SHARP if use_sharps else App.NOTE_NAMES_FLAT)
            try: self.builder_root_var.set(App.pc_to_name(App.name_to_pc(self.builder_root_var.get()), use_sharps))
            except (ValueError, AttributeError): self.builder_root_var.set(App.pc_to_name(0, use_sharps))
    def _log(self, msg: str):
        try:
            self.log.configure(state="normal"); self.log.insert("end", msg + "\n"); self.log.see("end"); self.log.configure(state="disabled")
        except: pass
        try:
            with open(LOGFILE, "a", encoding="utf-8") as f: f.write(msg + "\n")
        except: pass
    def _set_focus_tracker(self, entry_widget): self.last_focused_entry = entry_widget
    
    def _increase_measures(self):
        try: step = int(self.measures_entry.get())
        except (ValueError, TypeError): step = 4
        self.total_measures += step
        self._rebuild_measures()

    def _decrease_measures(self):
        try: step = int(self.measures_entry.get())
        except (ValueError, TypeError): step = 4
        self.total_measures = max(1, self.total_measures - step)
        self._rebuild_measures()
        
    def _rebuild_measures(self):
        if self._building: return
        self._building = True; existing_chords = [e.get() for e in getattr(self, "measure_entries", [])]
        try:
            for w in self.measures_frame.winfo_children(): w.destroy()
            for c in range(4): self.measures_frame.grid_columnconfigure(c, weight=1, uniform="measure_col")
            
            self.measure_entries: List[ctk.CTkEntry] = []
            for i in range(self.total_measures):
                row, col = i // 4, i % 4
                f = ctk.CTkFrame(self.measures_frame, border_width=1, fg_color=ctk.ThemeManager.theme["CTkFrame"]["top_fg_color"]); f.grid(row=row, column=col, padx=5, pady=5, sticky="nsew")
                f.grid_columnconfigure(1, weight=1)
                ctk.CTkLabel(f, text=f"{i+1}", font=self.font_bold, width=30).grid(row=0, column=0, padx=(8,0), pady=5)
                e = ctk.CTkEntry(f, font=self.font_main, border_width=0, fg_color="transparent"); e.grid(row=0, column=1, padx=(5,8), pady=5, sticky="ew")
                e.bind("<FocusIn>", lambda event, entry=e: self._set_focus_tracker(entry)); e.bind("<Button-3>", self._show_context_menu)
                if i < len(existing_chords): e.insert(0, existing_chords[i])
                self.measure_entries.append(e)
            if not self.last_focused_entry and self.measure_entries: self.last_focused_entry = self.measure_entries[0]
            self._log(f"Rebuilt for {self.total_measures} measures. Content preserved.")
        except Exception as e: self._log(f"Error rebuilding: {e}")
        finally: self._building = False
        
    def _clear_all_chords(self):
        lang = self.i18n[self.lang_code]
        if messagebox.askyesno(lang["clear_confirm_title"], lang["clear_confirm_message"]):
            for entry in self.measure_entries: entry.delete(0, "end")
            self._log("All measures cleared.")
    def _on_key_changed(self, *_):
        if self._suppress: return
        self._log(f"Key changed to {self.key_var.get()}. "); self._update_builder_roots(); self._convert_all_entries()
    def _on_mode_changed(self, *_):
        if self._suppress: return
        self._log(f"Mode changed to {self.mode_var.get()}. "); self._update_builder_roots(); self._convert_all_entries()
    def _convert_all_entries(self):
        mode, key = self.mode_var.get(), self.key_var.get(); is_to_degree = (mode == self.i18n[self.lang_code]["degree"])
        for e in getattr(self, "measure_entries", []):
            t = e.get().strip()
            if not t: continue
            try:
                parts = App.split_measure_text(t); out = []
                for p_str in parts:
                    parsed = App.parse_chord_symbol(p_str, key)
                    out.append(App.build_string_from_parsed(parsed, is_roman=is_to_degree, key=key))
                e.delete(0, "end"); e.insert(0, " ".join(out))
            except Exception as ex: self._log(f"Conversion error on '{t}': {ex}")
    def _reset_tensions(self):
        for var in self.tension_vars.values(): var.set(False)
        self._log("Tension selection reset.")
    def _on_build_and_insert(self):
        key = self.key_var.get()
        root_selection = self.builder_root_var.get()
        qual = self.builder_quality_var.get()
        selected_tensions = [t for t, v in self.tension_vars.items() if v.get()]
        
        qual_txt = qual if qual not in ["Major", "Minor"] else ('m' if qual == "Minor" else '')
        
        paren_tensions = [t for t in selected_tensions if re.search(r'[b#]', t)]
        text_tensions = [t for t in selected_tensions if not re.search(r'[b#]', t)]
        
        tens_txt = "".join(sorted(text_tensions, key=lambda x: int(re.sub(r'[^0-9]', '', x))))
        if selected_tensions and not any(c in qual_txt for c in ['7','M','m','d','a','s']):
            if not tens_txt: tens_txt = '7'
            
        paren_txt = f"({','.join(paren_tensions)})" if paren_tensions else ''
            
        chord_str_to_parse = f"{root_selection}{qual_txt}{tens_txt}{paren_txt}"
        
        parsed = App.parse_chord_symbol(chord_str_to_parse, key)
        is_degree_mode = self.mode_var.get() == self.i18n[self.lang_code]["degree"]
        sym = App.build_string_from_parsed(parsed, is_roman=is_degree_mode, key=key)
        
        target = self.last_focused_entry or (self.measure_entries[0] if self.measure_entries else None)
        if target:
            cur = target.get().strip(); target.delete(0, "end"); target.insert(0, (cur + " " + sym).strip())
            self._log(f"Inserted chord: {sym}")
        else: self._log("No measure entry to insert into.")
    def _on_generate_midi(self):
        try:
            path = filedialog.asksaveasfilename(title="Save MIDI",defaultextension=".mid", filetypes=[("MIDI file", "*.mid")])
            if not path: self._log("Save cancelled."); return
            mid = MidiFile(ticks_per_beat=480); track = MidiTrack(); mid.tracks.append(track)
            tpb = mid.ticks_per_beat; track.append(MetaMessage('set_tempo', tempo=bpm2tempo(120)))
            try: track.append(MetaMessage("key_signature", key=self.key_var.get()))
            except Exception: self._log(f"Skipping key_signature for '{self.key_var.get()}' (unsupported)")
            for e in getattr(self, "measure_entries", []):
                txt = e.get().strip()
                if not txt:
                    track.append(Message('note_off', note=0, velocity=0, time=4 * tpb)); continue
                chord_tokens = App.split_measure_text(txt); durations = App.duration_ticks_for_n(len(chord_tokens), tpb)
                for i, token in enumerate(chord_tokens):
                    try:
                        parsed = App.parse_chord_symbol(token, self.key_var.get())
                        notes = App.build_voicing(parsed, omit5_on_conflict=self.omit5_var.get(), omit_duplicated_bass=self.omit_bass_var.get())
                        chord_duration = durations[i]
                        for note_val in notes: track.append(Message('note_on', note=note_val, velocity=80, time=0))
                        for j, note_val in enumerate(notes): track.append(Message('note_off', note=note_val, velocity=0, time=chord_duration if j == 0 else 0))
                    except Exception as chord_err:
                        self._log(f"Skipping invalid chord '{token}': {chord_err}")
                        track.append(Message('note_off', note=0, velocity=0, time=durations[i]))
            mid.save(path); self._log(f"Saved MIDI: {path}"); messagebox.showinfo("MIDI", f"Saved: {path}")
        except Exception as e:
            self._log(f"FATAL Error generating MIDI: {e}"); messagebox.showerror("Error", f"Failed to generate MIDI:\n{e}")

if __name__ == "__main__":
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

                            call :update_status preparing -1 "설치 준비 중... (Preparing installer...)"
                            echo [%date% %time%] Starting Windows updater > "%LOG_FILE%"
                            timeout /t 2 /nobreak >nul

                            call :update_status waiting 12 "실행 중인 앱 종료 대기 중... (Waiting for app to close...)"
                            call :wait_for_parent
                            if errorlevel 1 goto restore

                            if exist "%OLD_APP_DIR%" (
                                rmdir /s /q "%OLD_APP_DIR%" >> "%LOG_FILE%" 2>&1
                            )

                            call :update_status installing 65 "기존 버전을 백업 중... (Backing up current version...)"
                            move "%APP_DIR%" "%OLD_APP_DIR%" >> "%LOG_FILE%" 2>&1
                            if errorlevel 1 goto restore

                            call :update_status installing 75 "새 파일을 복사 중... (Copying new files...)"
                            robocopy "%NEW_APP_DIR%" "%APP_DIR%" /MIR /NFL /NDL /NJH /NJS >> "%LOG_FILE%" 2>&1
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
                            if exist "%APP_DIR%" rmdir /s /q "%APP_DIR%" >> "%LOG_FILE%" 2>&1
                            if exist "%OLD_APP_DIR%" move "%OLD_APP_DIR%" "%APP_DIR%" >> "%LOG_FILE%" 2>&1
                            if exist "%UPDATE_FLAG%" del "%UPDATE_FLAG%" >nul 2>&1
                            exit /b 1

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

                        def _escape_for_py(value: str) -> str:
                            return (value
                                    .replace("\\", "\\\\")
                                    .replace('"', '\\"')
                                    .replace('{', '{{')
                                    .replace('}', '}}'))

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

    safe_message = str(message).replace('\n', ' ').replace('|', '/')
    tmp_path = status_path + '.tmp'
    try:
        with open(tmp_path, 'w', encoding='utf-8') as status_file:
            status_file.write(f"{state}|{percent_value}|{safe_message}")
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
        print(f"TUF update failed: {e}")
        print("Attempting fallback update check via GitHub API...")
        
        try:
            # GitHub API를 통해 최신 릴리즈 정보 가져오기
            api_url = "https://api.github.com/repos/kimtopseong/Chord-to-MIDI-GENERATOR/releases/latest"
            response = requests.get(api_url, timeout=5)
            response.raise_for_status() # HTTP 오류가 있으면 예외 발생
            
            latest_release = response.json()
            # tag_name에서 'v'를 제거하여 버전 번호만 추출
            latest_version_str = latest_release.get("tag_name", "v0.0.0").lstrip('v')
            
            # 현재 버전과 최신 버전 비교
            if parse_version(latest_version_str) > parse_version(CURRENT_VERSION):
                
                # 사용자에게 수동 업데이트 안내
                title = "수동 업데이트 필요 (Manual Update Required)"
                message = (
                    f"새로운 버전(v{latest_version_str})이 발견되었지만, 자동 업데이트에 실패했습니다.\n"
                    f"다운로드 페이지로 이동하시겠습니까?\n"
                    f"---\n"
                    f"A new version (v{latest_version_str}) was found, but automatic update failed.\n"
                    f"Would you like to go to the download page?"
                )
                if messagebox.askyesno(title, message):
                    # GitHub 릴리즈 페이지를 웹 브라우저로 열기
                    download_url = latest_release.get("html_url")
                    if download_url:
                        webbrowser.open(download_url)
        
        except requests.exceptions.RequestException as api_error:
            # 네트워크 오류 등으로 GitHub API 접근 실패 시
            print(f"GitHub API check failed: {api_error}")
        except Exception as fallback_error:
            # 기타 예외 처리
            print(f"An unexpected error occurred during fallback check: {fallback_error}")
    
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
