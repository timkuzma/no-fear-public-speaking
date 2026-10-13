"""JSONL diagnostics. Never serialize exception messages, request bodies or credentials."""
import datetime
import json
import logging
import re
import os


class SafeFormatter(logging.Formatter):
    def format(self, record):
        message=record.getMessage()
        fields={k:v for k,v in re.findall(r'\b(request|id|code|route|status|latency_ms)=([A-Za-z0-9_./:{}-]+)',message)}
        for key in ('request','id'):
            if key in fields and not re.fullmatch('[a-f0-9]{32}',fields[key]):fields.pop(key)
        if 'code' in fields and not re.fullmatch('[A-Z0-9_]{2,80}',fields['code']):fields.pop('code')
        # Template paths only: filenames and user-supplied URL queries are excluded.
        if 'route' in fields and ('?' in fields['route'] or not fields['route'].startswith('/api/')):fields.pop('route')
        result={'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),'level':record.levelname,
                'component':record.name,'release':os.getenv('APP_RELEASE','local'),'event':message.split(' ',1)[0] if re.fullmatch(r'[a-z_]+',message.split(' ',1)[0]) else 'runtime','data':fields}
        if record.exc_info:result['exception_type']=record.exc_info[0].__name__
        return json.dumps(result,ensure_ascii=False)


def configuration():
    return {'version':1,'disable_existing_loggers':False,'formatters':{'safe':{'()':'server.structured_logging.SafeFormatter'}},
            'handlers':{'default':{'class':'logging.StreamHandler','formatter':'safe','stream':'ext://sys.stdout'}},
            'root':{'handlers':['default'],'level':'INFO'},
            'loggers':{'uvicorn':{'handlers':['default'],'level':'INFO','propagate':False},'uvicorn.error':{'level':'INFO'},'uvicorn.access':{'handlers':['default'],'level':'WARNING','propagate':False}}}
