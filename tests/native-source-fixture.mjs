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
 run(`import sys,os,sqlite3,zlib,struct,binascii
from pathlib import Path
from contextlib import closing
sys.path.insert(0,os.environ['HERMES_SOURCE'])
from hermes_state import SessionDB
path=Path(sys.argv[1]);path.unlink()
with closing(SessionDB(path)) as db:
 db.create_session('fictional-session-01','desktop')
 db.set_session_title('fictional-session-01','Native source conversation')
 db.append_message('fictional-session-01','assistant','Native assistant preview from the real source API.')
 for i in range(2,44): db.append_message('fictional-session-01','tool','Fixture tool output')
 db.create_session('pruned-session','cli')
 db.set_session_title('pruned-session','Prunable source')
 assert db.append_message('pruned-session','assistant','Old assistant response')==44
 db.create_session('fictional-files','desktop')
 db.set_session_title('fictional-files','Meadow deliverables')
 db.append_message('fictional-files','user','Make a meadow survey report and illustration.')
 folder=path.parent/'workspaces'
 (folder/'meadow.md').write_text('Fictional meadow survey: three swallows.')
 (folder/'bundle.zip').write_bytes(b'PK fictional opaque archive')
 def chunk(kind,data): return struct.pack('>I',len(data))+kind+data+struct.pack('>I',binascii.crc32(kind+data)&0xffffffff)
 pixels=b''.join(b'\\x00'+bytes([70,120,90])*180 for _ in range(120))
 png=b'\\x89PNG\\r\\n\\x1a\\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',180,120,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(pixels))+chunk(b'IEND',b'')
 (folder/'meadow.png').write_bytes(png)
 db.append_message('fictional-files','assistant','Files ready.\\n'+'\\n'.join('MEDIA:'+str(folder/name) for name in ('meadow.md','meadow.png','bundle.zip')))
 db.append_message('fictional-files','user','FUTURE request must not be sent')
 db.get_messages('fictional-files')
 `);
 return {prune(){run(`import sqlite3,sys
with sqlite3.connect(sys.argv[1]) as db:
 db.execute("DELETE FROM messages WHERE session_id='pruned-session'")
 db.execute("DELETE FROM sessions WHERE id='pruned-session'")
`);},restore(){run(`import sqlite3,sys
with sqlite3.connect(sys.argv[1]) as db:
 db.execute("INSERT OR REPLACE INTO sessions(id,profile_name,title,source,last_activity_at,started_at) VALUES('pruned-session','default','Prunable source','cli',1,1)")
 db.execute("INSERT OR REPLACE INTO messages(id,session_id,role,content,timestamp) VALUES(44,'pruned-session','assistant','Old assistant response',1)")
`);}};
}
