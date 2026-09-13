import runpy, subprocess, sys

subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'requests'])
runpy.run_path('backtest/youtube_10_strategies.py', run_name='__main__')
