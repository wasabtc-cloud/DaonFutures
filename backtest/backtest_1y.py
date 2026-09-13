import os, runpy, subprocess, sys

subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'requests'])
runpy.run_path('backtest/youtube_10_strategies.py', run_name='__main__')
if os.path.exists('youtube_10_results.csv'):
    os.replace('youtube_10_results.csv', 'backtest_results.csv')
