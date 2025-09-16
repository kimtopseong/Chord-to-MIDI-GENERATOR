import tkinter
root = tkinter.Tk()

# 더 안정적인 방법인 'call'을 사용하여 Tcl/Tk 변수 값을 가져옵니다.
print(f"TCL_LIBRARY: {root.tk.call('set', 'tcl_library')}")
print(f"TK_LIBRARY: {root.tk.call('set', 'tk_library')}")