"""CatchWorld integrated microstructure logger.
Joins raw trade/book events and V2/V3 sensor outputs on one UTC timeline.
Research logging only; never emits trading decisions.
"""
from __future__ import annotations
import json, os
from pathlib import Path
from datetime import datetime, timezone
from typing import Any

class IntegratedLogger:
    def __init__(self, root=os.getenv('CW_LOG_ROOT','data/integrated_micro')):
        self.root=Path(root); self.root.mkdir(parents=True,exist_ok=True)
    def write(self, market:str, event_type:str, ts_ms:int, payload:dict[str,Any]):
        hour=datetime.fromtimestamp(ts_ms/1000,timezone.utc).strftime('%Y%m%d_%H')
        d=self.root/event_type; d.mkdir(parents=True,exist_ok=True)
        row={'ts_ms':int(ts_ms),'market':market,'event_type':event_type,**payload}
        with (d/f'{hour}.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n')
    def trade(self, raw, v2=None, v3=None):
        ts=int(raw.get('trade_ts_ms') or raw['recv_ms']); self.write(raw['market'],'trade',ts,{'raw':raw,'v2':v2,'v3':v3})
    def book(self, raw, v2=None, v3=None):
        ts=int(raw.get('timestamp') or raw['recv_ms']); self.write(raw['market'],'book',ts,{'raw':raw,'v2':v2,'v3':v3})
