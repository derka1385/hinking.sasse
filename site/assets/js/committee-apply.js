(() => {
  const form = document.getElementById('application');
  if (!form) return;
  const button = form.querySelector('button[type=submit]');
  const message = document.getElementById('application-message');
  const experience = form.elements.experience;
  let requestKey = crypto.randomUUID();
  let lastPayload = '';
  const say = (text, error = false) => { message.textContent = text; message.classList.toggle('is-error',error); };
  form.addEventListener('change', () => {
    experience.required = form.elements.hasExperience.value === 'yes';
    form.querySelectorAll('[aria-invalid]').forEach(el=>el.removeAttribute('aria-invalid'));
  });
  fetch('../site/data/committee-roles.json').then(response=>{
    if (!response.ok) throw new Error('roles');
    return response.json();
  }).then(meta=>{
    const container = document.getElementById('role-options');
    container.replaceChildren();
    for (const role of meta.roles) {
      const label = document.createElement('label'); label.className = 'role-option';
      const input = document.createElement('input'); input.type='checkbox'; input.name='roles'; input.value=role.id;
      const copy = document.createElement('span');
      const name = document.createElement('span'); name.className='role-option-name'; name.textContent=role.name;
      const description = document.createElement('span'); description.className='role-option-description'; description.textContent=role.description;
      copy.append(name,description); label.append(input,copy); container.append(label);
    }
    container.setAttribute('aria-busy','false'); button.disabled=false;
  }).catch(()=>say('We could not load the available roles. Please refresh the page and try again.',true));
  form.addEventListener('submit', async event=>{
    event.preventDefault();
    const values = new FormData(form);
    for (const name of ['interests','roles']) {
      if (!values.getAll(name).length) {
        say(name==='roles'?'Choose at least one role.':'Choose Hiking, Mountaineering or both.',true);
        const field=form.querySelector(`[name="${name}"]`); field.setAttribute('aria-invalid','true'); field.focus(); return;
      }
    }
    const payload={firstName:values.get('firstName'),lastName:values.get('lastName'),email:values.get('email'),programme:values.get('programme'),hasExperience:values.get('hasExperience'),experience:values.get('experience'),interests:values.getAll('interests'),roles:values.getAll('roles'),contactConsent:values.has('contactConsent'),website:values.get('website')};
    const serialized=JSON.stringify(payload);
    if (lastPayload && lastPayload!==serialized) requestKey=crypto.randomUUID();
    lastPayload=serialized; payload.requestKey=requestKey;
    button.disabled=true; button.textContent='Sending…'; say('Saving your application…');
    try {
      const response=await fetch('/api/committee/apply',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
      let data;try {data=await response.json();} catch {throw new Error('We could not send your application. Your answers are still on this page. Please try again.');}
      if (!response.ok) {
        for (const name of Object.keys(data.fields||{})) form.querySelector(`[name="${CSS.escape(name)}"]`)?.setAttribute('aria-invalid','true');
        throw new Error(data.error||'We could not send your application. Please try again.');
      }
      form.hidden=true; say('');
      const success=document.getElementById('application-success');
      success.querySelector('.application-reference').textContent='Application reference: '+data.reference;
      success.hidden=false; success.focus();
    } catch(error) {
      say(error instanceof TypeError?'We could not reach the application service. Your answers are still on this page. Please try again.':error.message,true);
      message.focus();
    } finally { button.disabled=false; button.textContent='Send application'; }
  });
})();
