// Fixture-only native SQLite setup. Never points at a real profile bank.
import {execFileSync} from 'node:child_process';
import {readdir,realpath} from 'node:fs/promises';
import {join,relative} from 'node:path';
export async function sourceFixture(scratch){
 const dir=(await readdir(scratch,{withFileTypes:true})).find(d=>d.isDirectory()&&d.name.startsWith('sv-'));
 if(!dir)throw Error('Owned fictional server home not found');
 const home=await realpath(join(scratch,dir.name,'home'));
 if(relative(await realpath(scratch),home).startsWith('..'))throw Error('Fixture escaped owned scratch');
 const run=script=>execFileSync(process.env.PYTHON||'python',['-c',script,join(home,'state.db')],{env:{...process.env,PYTHONDONTWRITEBYTECODE:'1'}});
 run(`import sqlite3,sys
with sqlite3.connect(sys.argv[1]) as db:
 for table,cols in {'sessions':{'title':'TEXT','source':'TEXT','started_at':'REAL','ended_at':'REAL','last_activity_at':'REAL','hidden':'INTEGER'},'messages':{'role':'TEXT','content':'TEXT','timestamp':'REAL','display_kind':'TEXT','observed':'INTEGER','_compressed_summary':'INTEGER'}}.items():
  existing={r[1] for r in db.execute('PRAGMA table_info('+table+')')}
  for col,kind in cols.items():
   if col not in existing: db.execute('ALTER TABLE '+table+' ADD COLUMN '+col+' '+kind)
 db.execute("UPDATE sessions SET title='Native source conversation',source='desktop',last_activity_at=1793400000 WHERE id='fictional-session-01'")
 db.execute("UPDATE messages SET role='assistant',content='Native assistant preview from the real source API.',timestamp=1793400100 WHERE id=1")
 db.execute("INSERT OR REPLACE INTO sessions(id,profile_name,title,source,last_activity_at) VALUES('pruned-session','default','Prunable source','cli',1)")
 db.execute("INSERT OR REPLACE INTO messages(id,session_id,role,content,timestamp) VALUES(44,'pruned-session','assistant','Old assistant response',1)")
 `);
 return {prune(){run(`import sqlite3,sys
with sqlite3.connect(sys.argv[1]) as db:
 db.execute("DELETE FROM messages WHERE session_id='pruned-session'")
 db.execute("DELETE FROM sessions WHERE id='pruned-session'")
`);},restore(){run(`import sqlite3,sys
with sqlite3.connect(sys.argv[1]) as db:
 db.execute("INSERT OR REPLACE INTO sessions(id,profile_name,title,source,last_activity_at) VALUES('pruned-session','default','Prunable source','cli',1)")
 db.execute("INSERT OR REPLACE INTO messages(id,session_id,role,content,timestamp) VALUES(44,'pruned-session','assistant','Old assistant response',1)")
`);}};
}
