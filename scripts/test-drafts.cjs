'use strict';
const assert=require('node:assert/strict');
global.indexedDB=require('../artifacts/qa/node_modules/fake-indexeddb').indexedDB;
const A=require('../averias/shared.js');
(async()=>{
  const storage=A.drafts(),id=crypto.randomUUID(),photo=new Blob(['photo bytes'],{type:'image/jpeg'});
  await storage.put({id,photo,payload:{description:'Junta rota'},attempted:false});
  const reopened=A.drafts();let draft=await reopened.get(id);
  assert.equal(await draft.photo.text(),'photo bytes');assert.equal(draft.payload.description,'Junta rota');
  draft.attempted=true;await reopened.put(draft);assert.equal((await storage.all()).length,1);
  assert.equal((await A.drafts().get(id)).attempted,true);
  await storage.remove(id);assert.equal((await storage.all()).length,0);
  console.log('PASS: durable draft payload/photo across handles, update without duplicates, attempted-send flag, remove');
})().catch(error=>{console.error(error);process.exitCode=1;});
