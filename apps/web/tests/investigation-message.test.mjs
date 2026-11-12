import {test} from 'node:test';
import assert from 'node:assert/strict';
import {composeInvestigationMessage} from '../app/investigation-message.ts';

test('text mode keeps the original wording and does not rewrite URLs',()=>{
 assert.deepEqual(composeInvestigationMessage('  某服务是否永久免费？  ','text'),{ok:true,message:'某服务是否永久免费？'});
 assert.equal(composeInvestigationMessage('https://example.com/claim','text').message,'https://example.com/claim');
});

test('url mode wraps a public https page and rejects unsafe or incomplete addresses',()=>{
 const ok=composeInvestigationMessage('https://docs.example.com/terms#top','url');
 assert.equal(ok.ok,true);
 assert.equal(ok.message,'请核查该公开网页中的具体说法：https://docs.example.com/terms');
 assert.equal(composeInvestigationMessage('http://example.com/','url').ok,false);
 assert.equal(composeInvestigationMessage('https://user:secret@example.com/','url').ok,false);
 assert.equal(composeInvestigationMessage('javascript:alert(1)','url').ok,false);
 assert.equal(composeInvestigationMessage('example.com/path','url').ok,false);
});
