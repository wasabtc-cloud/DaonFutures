import os, runpy

# Temporary runner for the 10 YouTube-style strategy comparison.
runpy.run_path('backtest/youtube_10_strategies.py', run_name='__main__')
if os.path.exists('youtube_10_results.csv'):
    os.replace('youtube_10_results.csv', 'backtest_results.csv')
