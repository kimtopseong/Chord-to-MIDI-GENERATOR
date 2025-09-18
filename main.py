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
CURRENT_VERSION = "1.1.2"

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
    @staticmethod
    def resource_path(relative_path: str) -> str:
        """Safe resource lookup for dev & PyInstaller runtime.
        On macOS .app, base is Contents/MacOS (next to the executable)."""
        import sys
        from pathlib import Path
        if getattr(sys, 'frozen', False):
            if sys.platform == 'darwin' and '.app/' in sys.executable:
                base = Path(sys.executable).resolve().parent
            else:
                base = Path(getattr(sys, '_MEIPASS', Path(sys.executable).resolve().parent))
        else:
            base = Path(__file__).resolve().parent
        return str(base / relative_path)

    def __init__(self, *args, splash_root=None, **kwargs):
        kwargs.pop('splash_root', None)
        super().__init__(*args, **kwargs)
        self.splash_root = splash_root

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
    @staticmethod
    def resource_path(relative_path: str) -> str:
        """
        Locate bundled resources reliably across dev & PyInstaller runtime.
        On macOS .app, base is Contents/MacOS (next to the executable).
        """
        import sys
        from pathlib import Path
from pathlib import Path
        if getattr(sys, 'frozen', False):
            # macOS app bundle
            if sys.platform == 'darwin' and '.app/' in sys.executable:
                base = Path(sys.executable).resolve().parent
            else:
                base = Path(getattr(sys, '_MEIPASS', Path(sys.executable).resolve().parent))
        else:
            base = Path(__file__).resolve().parent
        return str(base / relative_path)

    app.mainloop()