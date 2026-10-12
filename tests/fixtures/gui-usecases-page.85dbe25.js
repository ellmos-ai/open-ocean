    (() => {
      const byId = id => document.getElementById(id);
      const api = '/api/usecases';
      let rows = [];
      let selectedId = null;
      let editorId = null;
      const message = (id, value) => { const node=byId(id); node.textContent=value || ''; node.hidden=!value; };
      const label = result => result === 'pass' ? 'Definition geprüft' : result === 'fail' ? 'Definition unvollständig' : 'Prüfung ausstehend';
      const display = value => value == null || value === '' ? '–' : String(value);
      const validId = value => Number.isSafeInteger(Number(value)) && Number(value) > 0;

      async function request(url, options) {
        const response = await fetch(url, options);
        const body = await response.json().catch(() => ({}));
        if (!response.ok || body.success !== true) throw new Error(body.detail || body.error || `API nicht erreichbar (HTTP ${response.status}).`);
        return body;
      }

      async function load(selected = selectedId) {
        message('uc-list-error', '');
        byId('uc-count').textContent = 'Lade Definitionen…';
        try {
          const body = await request(api);
          if (!Array.isArray(body.usecases) || !body.stats) throw new Error('Ungültige Usecase-Antwort.');
          rows = body.usecases.filter(row => validId(row.id));
          const stats = body.stats;
          for (const [key, value] of [['total',stats.total],['pass',stats.pass],['fail',stats.fail],['pending',stats.pending]]) {
            byId('uc-' + key).textContent = Number.isSafeInteger(value) && value >= 0 ? String(value) : '–';
          }
          const options = byId('uc-workflow-options'); options.replaceChildren();
          for (const name of new Set(rows.map(row => row.workflow_name).filter(name => typeof name === 'string' && name.trim()))) {
            const option = document.createElement('option'); option.value=name; options.append(option);
          }
          renderList();
          if (selected && rows.some(row => Number(row.id) === Number(selected))) await open(Number(selected));
          else if (selected) clearDetail();
        } catch (cause) {
          rows=[];
          for (const key of ['total','pass','fail','pending']) byId('uc-' + key).textContent='–';
          byId('uc-list').replaceChildren();
          byId('uc-count').textContent='Keine Daten geladen';
          message('uc-list-error', cause instanceof Error ? cause.message : 'Usecases konnten nicht geladen werden.');
        }
      }

      function renderList() {
        const query = byId('uc-search').value.trim().toLocaleLowerCase('de');
        const found = rows.filter(row => [row.title,row.description,row.workflow_name].some(value => String(value || '').toLocaleLowerCase('de').includes(query)));
        const list=byId('uc-list'); list.replaceChildren();
        byId('uc-count').textContent = `${found.length} von ${rows.length} Definitionen`;
        if (!found.length) {
          const p=document.createElement('p');p.className='uc-muted';p.textContent=rows.length ? 'Keine passende Definition.' : 'Noch keine Usecases gespeichert.';list.append(p);return;
        }
        for (const row of found) {
          const button=document.createElement('button');button.type='button';button.dataset.id=String(row.id);
          button.setAttribute('aria-current',String(Number(row.id)===selectedId));
          const title=document.createElement('strong');title.textContent=display(row.title);
          const secondary=document.createElement('small');secondary.textContent=`${display(row.workflow_name)} · ${label(row.test_result)}`;
          button.append(title,secondary);button.addEventListener('click',()=>open(Number(row.id)));list.append(button);
        }
      }

      function clearDetail() {
        selectedId=null;byId('uc-empty').hidden=false;byId('uc-detail-content').hidden=true;renderList();
      }
      async function open(id) {
        if (!validId(id)) return;
        message('uc-action-status','');
        try {
          const body=await request(`${api}/${encodeURIComponent(id)}`);
          const item=body.usecase;
          if (!item || Number(item.id)!==id) throw new Error('Usecase-Detail stimmt nicht mit der ID überein.');
          selectedId=id;byId('uc-empty').hidden=true;byId('uc-detail-content').hidden=false;
          for (const [name,value] of Object.entries({id:`Usecase #${id}`,title:display(item.title),workflow:display(item.workflow_name),
            result:label(item.test_result),score:item.test_score == null ? '–' : `${item.test_score} %`,
            tested:display(item.last_tested),author:display(item.created_by),updated:display(item.updated_at),
            description:display(item.description),input:display(item.test_input),expected:display(item.expected_output)})) {
            byId('uc-' + name).textContent=value;
          }
          renderList();
          return item;
        } catch (cause) {
          message('uc-list-error',cause instanceof Error ? cause.message : 'Detail konnte nicht geladen werden.');
          return null;
        }
      }

      function editor(item) {
        editorId=item?.id ?? null;
        const form=byId('uc-editor-form');form.reset();message('uc-editor-error','');
        byId('uc-editor-title').textContent=editorId ? 'Usecase bearbeiten' : 'Neuer Usecase';
        for (const field of ['title','description','workflow_name','test_input','expected_output']) form.elements[field].value=String(item?.[field] || '');
        byId('uc-editor').showModal();form.elements.title.focus();
      }
      byId('uc-create').addEventListener('click',()=>editor(null));
      byId('uc-edit').addEventListener('click',async()=>{if(selectedId){const item=await open(selectedId);if(item)editor(item);}});
      for(const id of ['uc-editor-close','uc-editor-cancel'])byId(id).addEventListener('click',()=>byId('uc-editor').close());
      byId('uc-refresh').addEventListener('click',()=>load());
      byId('uc-search').addEventListener('input',renderList);

      byId('uc-editor-form').addEventListener('submit',async event=>{
        event.preventDefault();const form=event.currentTarget;if(!form.reportValidity())return;
        const submit=form.querySelector('button[type="submit"]');submit.disabled=true;message('uc-editor-error','');
        const values=new FormData(form);
        const payload=Object.fromEntries(['title','description','workflow_name','test_input','expected_output'].map(key=>[key,String(values.get(key)||'').trim()]));
        try {
          const id=editorId;
          const body=await request(id ? `${api}/${encodeURIComponent(id)}` : api,
            {method:id?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
          const savedId=id || Number(body.id);
          if(!validId(savedId))throw new Error('Speichern gemeldet, aber keine gültige ID zurückgegeben.');
          const check=await request(`${api}/${encodeURIComponent(savedId)}`);
          if(!check.usecase || ['title','description','workflow_name','test_input','expected_output'].some(key=>String(check.usecase[key]||'').trim()!==payload[key]))
            throw new Error('Speichern gemeldet, der Kontrollabruf weicht jedoch ab.');
          byId('uc-editor').close();await load(savedId);
        }catch(cause){message('uc-editor-error',cause instanceof Error?cause.message:'Usecase konnte nicht gespeichert werden.');}
        finally{submit.disabled=false;}
      });

      byId('uc-check').addEventListener('click',async()=>{
        if(!selectedId)return;
        if(!confirm('Nur die Usecase-Definition prüfen? Workflow und Modell werden nicht ausgeführt; der Prüfstatus wird gespeichert.'))return;
        const button=byId('uc-check');button.disabled=true;message('uc-action-status','Prüfe Definition…');
        try {
          const body=await request(`${api}/${encodeURIComponent(selectedId)}/test`,{method:'POST'});
          await load(selectedId);
          message('uc-action-status',`Definitionsprüfung gespeichert: ${label(body.result)}. Kein Workflow wurde ausgeführt.`);
        }catch(cause){message('uc-action-status',cause instanceof Error?cause.message:'Definitionsprüfung fehlgeschlagen.');}
        finally{button.disabled=false;}
      });
      byId('uc-check-all').addEventListener('click',async()=>{
        if(!rows.length)return;
        if(!confirm(`${rows.length} Usecase-Definitionen prüfen und ihren Prüfstatus speichern? Kein Workflow wird ausgeführt.`))return;
        const button=byId('uc-check-all');button.disabled=true;message('uc-list-error','');
        try {
          const body=await request(`${api}/test-all`,{method:'POST'});
          if(!Number.isSafeInteger(body.total))throw new Error('Ungültige Prüfantwort.');
          await load();
          message('uc-page-status',`${body.total} Definitionen geprüft. Kein Workflow wurde ausgeführt.`);
        }catch(cause){message('uc-list-error',cause instanceof Error?cause.message:'Definitionsprüfung fehlgeschlagen.');}
        finally{button.disabled=false;}
      });
      byId('uc-delete').addEventListener('click',async()=>{
        if(!selectedId)return;
        const id=selectedId;
        if(!confirm(`Usecase #${id} wirklich löschen? Diese Aktion entfernt die gespeicherte Definition.`))return;
        const button=byId('uc-delete');button.disabled=true;message('uc-action-status','');
        try {
          await request(`${api}/${encodeURIComponent(id)}`,{method:'DELETE'});
          const response=await fetch(`${api}/${encodeURIComponent(id)}`);
          const check=await response.json().catch(()=>({}));
          if(!response.ok || check.success!==false || check.error!=='Nicht gefunden')
            throw new Error('Löschung gemeldet, aber der Kontrollabruf ist nicht eindeutig. Bitte Daten prüfen.');
          clearDetail();await load(null);
        }catch(cause){message('uc-action-status',cause instanceof Error?cause.message:'Usecase konnte nicht gelöscht werden.');}
        finally{button.disabled=false;}
      });
      load();
    })();
