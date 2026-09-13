import os, runpy, subprocess, sys

subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'requests'])
runpy.run_path('backtest/upbit_moneyflow_v4.py', run_name='__main__')
