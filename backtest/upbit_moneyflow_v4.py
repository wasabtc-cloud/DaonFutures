import os,sys
ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path: sys.path.insert(0,ROOT)
from backtest import upbit_moneyflow_v2 as base

# V4 100X research: start with 1M KRW and preserve the validated no-lookahead engine.
# Core change vs v3: let strong trends run with TRAIL instead of forcing 3R exits.
base.START_CAPITAL=1_000_000.0
base.TOP_DAILY=5
base.MAX_CANDIDATES=35

_orig=base.run_variant
def run_variant_v4(data, entries, mode):
    # v2 TRAIL arms at 2R, moves stop to breakeven, then follows EMA20.
    return _orig(data, entries, 'TRAIL')

base.run_variant=run_variant_v4

if __name__=='__main__':
    base.main()
