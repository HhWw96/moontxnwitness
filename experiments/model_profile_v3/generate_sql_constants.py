"""Freeze reviewed SQL text into the independent MoonBit source verifier.

Only exact SQL constants are shared. The MoonBit verifier separately derives
parameters, native cells, deliveries, source chains, lifecycle and model facts.
Default check never modifies a file. No database or Moon compiler is invoked.
"""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'integrations/python'))
from moontxnwitness_capture.profiles.model_sql import ModelScope,ddl,control_sql


def render():
    literal=lambda s:json.dumps(s,ensure_ascii=False)
    scopes=[ModelScope('mtw_template_schema','append-list-v1',('x',)),ModelScope('mtw_template_schema','relation-set-v1',(1,))]
    output=['///|','/// Reviewed exact SQL constants. Regenerate/check with experiments/model_profile_v3/generate_sql_constants.py.',
        'fn model_ddl_v3(schema : String, is_list : Bool) -> Array[String] raise {','  let templates = if is_list {','    [']
    for i,scope in enumerate(scopes):
        sqls=ddl(scope)
        output.append('      '+literal(sqls[0])+', '+literal(sqls[1])+',')
        output.extend('      '+literal(sql)+',' for sql in sqls[2:])
        output+=['    ]']
        if i==0:output+=['  } else {','    [']
    output+=['  }','  templates.map(text => {','    text.replace_all(',
        '      old="\\\"mtw_template_schema\\\"",','      new=v3_dislock_quote(schema),','    )','  })','}','',
        '///|','fn model_control_sql_v3(','  name : String,','  schema : String,','  is_list : Bool,',') -> String raise {',
        '  let text = match (is_list, name) {']
    for is_list,scope in zip(('true','false'),scopes):
        for name,sql in control_sql(scope).items():
            output+=['    ('+is_list+', '+literal(name)+') =>','      '+literal(sql)]
    output+=['    _ => fail("Unknown configured model control SQL")','  }',
        '  text.replace_all(old="\\\"mtw_template_schema\\\"", new=v3_dislock_quote(schema))','}','']
    return '\n'.join(output)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--write',action='store_true');args=parser.parse_args()
    path=ROOT/'src/model_profile_sql_v3.mbt';text=render()
    if args.write:path.write_bytes(text.encode())
    elif not path.exists() or path.read_bytes()!=text.encode():raise SystemExit('Frozen model SQL constants differ')
    print('Exact model SQL constants agree')


if __name__=='__main__':main()
