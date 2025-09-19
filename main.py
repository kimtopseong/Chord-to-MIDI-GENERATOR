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
from dataclasses import dataclass, field
from typing import List, Optional
import os
import platform

import tkinter as tk
from tkinter import PhotoImage, filedialog, messagebox
import customtkinter as ctk
from mido import Message, MidiFile, MidiTrack, MetaMessage, bpm2tempo

APP_TITLE = "Chord-to-MIDI-GENERATOR"
LOGFILE = "chord_to_midi.log"
CURRENT_VERSION = "1.1.52"

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

        if 'sus4' in rest_mut: quality = 'sus4'; rest_mut = rest_mut.replace('sus4', '')
        elif 'sus2' in rest_mut: quality = 'sus2'; rest_mut = rest_mut.replace('sus2', '')
        elif 'blk' in rest_mut: quality = 'blk'; rest_mut = rest_mut.replace('blk', '')
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
            # Intervals from C(0) are D(4), F#(6), A#(10)
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
    from tuf.ngclient import Updater
    from tuf.ngclient.config import UpdaterConfig

    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger('tuf').setLevel(logging.DEBUG)

    try:
        APP_NAME = 'Chord-to-MIDI-GENERATOR'
        writable_dir = Path.home() / f'.{APP_NAME.lower().replace(" ", "_")}'
        metadata_dir = writable_dir / 'metadata'
        os.makedirs(metadata_dir, exist_ok=True)
        bundled_root_json_path_str = App.resource_path('root.json')
        
        shutil.copy(bundled_root_json_path_str, metadata_dir / 'root.json')

        if getattr(sys, 'frozen', False):
            app_install_dir = Path(sys.executable).parent.parent.parent
        else:
            app_install_dir = Path(__file__).parent
        
        METADATA_BASE_URL = 'https://kimtopseong.github.io/Chord-to-MIDI-GENERATOR/metadata'
        TARGET_BASE_URL = 'https://github.com/kimtopseong/Chord-to-MIDI-GENERATOR/releases/download/'
        target_dir = writable_dir / 'targets'
        os.makedirs(target_dir, exist_ok=True)
        
        updater = Updater(
            metadata_dir=str(metadata_dir),
            metadata_base_url=METADATA_BASE_URL,
            target_dir=str(target_dir),
            target_base_url=TARGET_BASE_URL,
            config=UpdaterConfig(max_root_rotations=10) # Allow more root rotations
        )
        updater.refresh()
        
        # Find the latest available target
        latest_target = None
        try:
            # Access the trusted metadata set through the updater's private attribute
            trusted_set = updater._trusted_set
            all_targets = trusted_set.targets.targets
            if all_targets:
                latest_target = max(all_targets.values(), key=lambda t: t.version)

        except Exception as e:
            print(f"Could not find targets: {e}")

        if latest_target and latest_target.version > CURRENT_VERSION:
            if messagebox.askyesno("Update available", f"An update to version {latest_target.version} is available. Do you want to install it?"):
                updater.download_target(latest_target)
                updater.install_on_exit([sys.executable] + sys.argv)
                sys.exit(0)

    except Exception as e:
        print(f"Error during update check: {e}")
    
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