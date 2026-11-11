/* Use the server's manifest resolver, with the same explicitly selected Python. */
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';

export function savedRepos(root,peer=process.env.SAVED_PEER_REPO){
 return JSON.parse(execFileSync(process.env.PYTHON||'python',[
  fileURLToPath(new URL('./saved_fixture_repos.py',import.meta.url)),root,
  ...(peer===undefined?[]:[peer]),
 ],{encoding:'utf8'}));
}

export function savedRoleFiles(id){
 if(id==='conversation-bookmarks')return ['ui/Bookmarks.jsx','ui/BookmarkEditor.jsx'];
 if(id==='delivery-shelf')return ['ui/Shelf.jsx'];
 throw new Error('Saved repositories: unsupported identity '+id);
}
