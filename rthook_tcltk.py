import os
import sys

# When running as a PyInstaller --onefile bundle, files are extracted to a temp dir
# referenced by sys._MEIPASS. We need to tell Tcl/Tk where to find their init scripts.
if getattr(sys, 'frozen', False):
    base = sys._MEIPASS
    os.environ['TCL_LIBRARY'] = os.path.join(base, 'tcl', 'tcl8.6')
    os.environ['TK_LIBRARY'] = os.path.join(base, 'tk', 'tk8.6')
