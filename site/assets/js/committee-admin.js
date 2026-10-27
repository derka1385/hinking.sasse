(() => {
  const $ = selector => document.querySelector(selector);
  const statuses={new:'New',reviewed:'Reviewed',shortlisted:'Shortlisted',interview:'Interview scheduled',accepted:'Accepted','not-selected':'Not selected'};
  const state={meta:null,offset:0,total:0,current:null,drafts:[],loggedIn:false};
  const el=(tag,attrs={},...children)=>{
    const node=document.createElement(tag);
    for(const [key,value] of Object.entries(attrs)) {
      if(key==='class') node.className=value;
      else node.setAttribute(key,String(value));
    }
    node.append(...children.flat()); return node;
  };
  const roleName=id=>state.meta.roles.find(r=>r.id===id)?.name||id;
  const showMessage=(text,error=false)=>{const node=$('#admin-message');node.textContent=text;node.classList.toggle('is-error',error);};
  function showLogin(){
    state.loggedIn=false;state.current=null;state.drafts=[];state.offset=0;
    $('#login-view').hidden=false;$('#admin-view').hidden=true;$('#logout').hidden=true;
    $('#application-list').replaceChildren();$('#application-detail').replaceChildren();$('#agenda-list').replaceChildren();
    $('#settings-form').reset();$('#filters').reset();$('#plan-preview').replaceChildren();
    $('#plan-preview').hidden=true;$('#confirm-plan').hidden=true;
    $('#applications-summary').replaceChildren();$('#page-count').textContent='';
    returnToList();
  }
  async function api(path,method='GET',body){
    let response;
    try {response=await fetch('/api/committee/'+path,{method,credentials:'same-origin',headers:{'Accept':'application/json',...(body?{'Content-Type':'application/json'}:{})},...(body?{body:JSON.stringify(body)}:{})});}
    catch {throw new Error('The committee service could not be reached. Please try again.');}
    let data;try {data=await response.json();} catch {throw new Error('The committee service is unavailable. Please try again.');}
    if(response.status===401&&path!=='login') showLogin();
    if(!response.ok){const error=new Error(data.error||'The request could not be completed.');error.status=response.status;throw error;}
    return data;
  }
  function select(name,options,value){
    const node=el('select',{name});
    for(const [id,label] of options) node.append(el('option',{value:id},label));
    if(value!==undefined)node.value=value;return node;
  }
  function input(name,type,value='') {return el('input',{name,type,value});}
  function label(title,control,wide=false){return el('label',wide?{class:'span-all'}:{},title,control);}
  function activate(panel){
    for(const button of document.querySelectorAll('[data-panel]')) {
      const active=button.dataset.panel===panel;
      if(active)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');
      $('#panel-'+button.dataset.panel).hidden=!active;
    }
    showMessage('');
  }
  function returnToList(){
    state.current=null;$('#application-detail').hidden=true;
    $('#application-list').hidden=false;$('#filters').hidden=false;$('.pagination').hidden=false;
  }
  const stockholm=value=>new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Stockholm',dateStyle:'medium',timeStyle:'short'}).format(new Date(value));
  function tomorrow(time){
    const date=new Intl.DateTimeFormat('sv-SE',{timeZone:'Europe/Stockholm',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(Date.now()+86400000));
    return date+'T'+time;
  }
  async function loadApplications(){
    const query=new URLSearchParams(new FormData($('#filters')));query.set('offset',state.offset);
    const data=await api('applications?'+query);if(!state.loggedIn)return;state.total=data.total;
    const summary=$('#applications-summary');summary.replaceChildren();
    const total=Object.values(data.counts).reduce((sum,n)=>sum+n,0);
    for(const [number,name] of [[total,'applications'],[data.counts.shortlisted||0,'shortlisted'],[data.counts.interview||0,'with an interview']]) summary.append(el('span',{},el('strong',{},String(number)),' '+name));
    const list=$('#application-list');list.replaceChildren();
    if(!data.items.length)list.append(el('p',{class:'empty-state'},data.total?'No applications on this page.':'No applications match these filters. New applications will appear here.'));
    for(const app of data.items){
      const button=el('button',{type:'button',class:'application-row'},
        el('span',{},el('strong',{},app.first_name+' '+app.last_name),el('small',{},app.email)),
        el('span',{class:'row-role'},app.roles.map(roleName).join(' · ')),
        el('span',{class:'row-programme'},app.programme),
        el('span',{class:'row-status'},el('span',{class:'status-label'},statuses[app.status]||app.status)),
        el('span',{class:'row-arrow','aria-hidden':'true'},'→'));
      button.addEventListener('click',()=>openApplication(app.id).catch(error=>showMessage(error.message,true)));
      list.append(button);
    }
    $('#page-count').textContent=data.total?`${data.offset+1}–${Math.min(data.offset+data.items.length,data.total)} of ${data.total}`:'0 applications';
    $('#previous-page').disabled=state.offset===0;$('#next-page').disabled=state.offset+data.limit>=data.total;
  }
  async function openApplication(id){
    const app=await api('applications/'+encodeURIComponent(id));if(!state.loggedIn)return;state.current=app;
    $('#application-list').hidden=true;$('#filters').hidden=true;$('.pagination').hidden=true;
    const detail=$('#application-detail');detail.replaceChildren();detail.hidden=false;
    const back=el('button',{type:'button',class:'text-button'},'Back to applications');back.addEventListener('click',returnToList);
    detail.append(back,el('div',{class:'detail-heading'},el('h2',{},app.first_name+' '+app.last_name)));
    const facts=el('dl',{class:'detail-meta'});
    for(const [title,value] of [['Email',app.email],['Programme',app.programme],['Interests',app.interests.join(' · ')],['Received',stockholm(app.created_at)],['Reference',app.reference],['Applied roles',app.roles.map(roleName).join(' · ')]]) facts.append(el('div',{},el('dt',{},title),el('dd',{},value)));
    detail.append(facts,el('h3',{},'Previous experience'),el('p',{class:'detail-experience'},(app.has_experience==='yes'?'Yes':'Not yet')+'\n'+(app.experience||'No additional details.')));
    const review=el('section',{class:'detail-section'},el('h3',{},'Review'));
    const reviewForm=el('form',{class:'form-grid'});
    const status=select('status',Object.entries(statuses),app.status);
    const notes=el('textarea',{name:'notes',rows:'5',maxlength:'8000'});notes.value=app.notes;
    const save=el('button',{class:'recruit-button',type:'submit'},'Save review');
    const reviewMessage=el('p',{class:'field-hint','role':'status'});
    reviewForm.append(label('Status',status),label('Private committee notes',notes,true),el('div',{class:'span-all'},save),el('div',{class:'span-all'},reviewMessage));
    reviewForm.addEventListener('submit',async event=>{
      event.preventDefault();save.disabled=true;reviewMessage.textContent='Saving…';
      try {state.current=await api('applications/'+id,'PATCH',{status:status.value,notes:notes.value});await loadApplications();reviewMessage.textContent='Review saved.';}
      catch(error){reviewMessage.textContent=error.message;}finally{save.disabled=false;}
    });
    review.append(reviewForm);detail.append(review);
    const booking=el('section',{class:'detail-section'},el('h3',{},'Schedule an interview'));
    const bookingForm=el('form',{class:'form-grid'});
    const role=select('roleId',app.roles.map(id=>[id,roleName(id)]));
    role.required=true;
    const start=input('localStart','datetime-local',tomorrow('10:00'));start.required=true;
    const duration=input('duration','number','20');duration.min='10';duration.max='120';duration.required=true;
    const interviewer=input('interviewer','text','Committee');interviewer.required=true;interviewer.maxLength=120;
    const location=input('location','text');location.maxLength=500;
    const book=el('button',{class:'recruit-button',type:'submit'},'Save interview');
    const bookingMessage=el('p',{class:'field-hint','role':'status'});
    bookingForm.append(label('Interview role',role),label('Start · Stockholm time',start),label('Length · minutes',duration),label('Interviewer or panel',interviewer),label('Location or meeting link',location,true),el('div',{class:'span-all'},book),el('div',{class:'span-all'},bookingMessage));
    bookingForm.addEventListener('submit',async event=>{
      event.preventDefault();book.disabled=true;bookingMessage.textContent='Saving…';
      try {
        await api('interviews','POST',{interviews:[{applicationId:app.id,roleId:role.value,localStart:start.value,duration:Number(duration.value),interviewer:interviewer.value,location:location.value}]});
        state.current.status='interview';status.value='interview';await Promise.all([loadApplications(),loadAgenda()]);
        bookingMessage.textContent='Interview saved. It is in the agenda and calendar export. No email invitation has been sent to the candidate.';
      }catch(error){bookingMessage.textContent=error.message;}finally{book.disabled=false;}
    });
    booking.append(bookingForm);detail.append(booking);detail.focus();
  }
  async function loadAgenda(){
    const data=await api('interviews');if(!state.loggedIn)return;const list=$('#agenda-list');list.replaceChildren();
    if(!data.items.length)list.append(el('p',{class:'empty-state'},'No interviews scheduled yet. Shortlist applicants, then create a session below or book a slot from their application.'));
    for(const item of data.items){
      const cancel=el('button',{type:'button',class:'text-button agenda-cancel'},'Cancel');
      cancel.setAttribute('aria-label','Cancel interview with '+item.first_name+' '+item.last_name);
      cancel.addEventListener('click',async()=>{
        if(!window.confirm('Cancel this interview? The candidate will not be emailed.'))return;
        cancel.disabled=true;
        try {
          await api('interviews/'+item.id,'DELETE',{});await Promise.all([loadAgenda(),loadApplications()]);
          if(state.current?.id===item.application_id){const current=await api('applications/'+item.application_id);state.current.status=current.status;$('#application-detail [name=status]').value=current.status;}
          showMessage('Interview cancelled.');
        }catch(error){showMessage(error.message,true);cancel.disabled=false;}
      });
      list.append(el('article',{class:'agenda-item'},
        el('div',{},el('strong',{},stockholm(item.starts_at)),el('p',{},'Until '+new Intl.DateTimeFormat('en-GB',{timeZone:'Europe/Stockholm',hour:'2-digit',minute:'2-digit'}).format(new Date(item.ends_at)))),
        el('div',{class:'agenda-person'},el('strong',{},item.first_name+' '+item.last_name),el('p',{},item.email)),
        el('div',{class:'agenda-role'},roleName(item.role_id),el('p',{},item.interviewer+(item.location?' · '+item.location:''))),cancel));
    }
  }
  async function loadSettings(){
    const data=await api('settings');if(!state.loggedIn)return;const form=$('#settings-form');
    for(const [key,value] of Object.entries(data))if(form.elements.namedItem(key))form.elements.namedItem(key).value=value;
    form.elements.smtp_password.value='';
    $('#password-hint').textContent=data.smtp_password_set?'A password is saved. Leave blank to keep it.':'No password is saved yet.';
    const counts=data.mail_counts;
    $('#mail-summary').textContent=`Sent: ${counts.sent||0} · Queued: ${(counts.pending||0)+(counts.sending||0)} · Failed: ${counts.failed||0}`+(data.last_mail_error?' · Last delivery error: '+data.last_mail_error:'');
    $('#test-email').disabled=!data.smtp_ready;$('#retry-email').disabled=!data.smtp_ready;
    const notice=$('#email-notice');notice.hidden=data.smtp_ready&&!data.last_mail_error;
    notice.textContent=!data.smtp_ready?'Applications are saved. Email notifications are waiting for an SMTP connection in Email settings.':'Email delivery needs attention. Check Email settings for the last delivery error.';
  }
  async function refresh(){await Promise.all([loadApplications(),loadAgenda(),loadSettings()]);}
  async function signedIn(){
    state.loggedIn=true;$('#login-view').hidden=true;$('#admin-view').hidden=false;$('#logout').hidden=false;
    await refresh();
    const id=location.hash.slice(1);
    if(/^[a-f0-9-]{36}$/.test(id))await openApplication(id);
  }
  $('#login-form').addEventListener('submit',async event=>{
    event.preventDefault();const form=event.currentTarget,button=form.querySelector('button');button.disabled=true;$('#login-message').textContent='Signing in…';
    try {await api('login','POST',{password:form.elements.password.value});form.reset();$('#login-message').textContent='';await signedIn();}
    catch(error){$('#login-message').textContent=error.message;$('#login-message').classList.add('is-error');}
    finally{button.disabled=false;}
  });
  $('#logout').addEventListener('click',async()=>{try{await api('logout','POST',{});}catch{}showLogin();});
  $('#refresh').addEventListener('click',()=>refresh().then(()=>showMessage('Workspace refreshed.')).catch(error=>showMessage(error.message,true)));
  document.querySelectorAll('[data-panel]').forEach(button=>button.addEventListener('click',()=>activate(button.dataset.panel)));
  $('#filters').addEventListener('submit',event=>{event.preventDefault();state.offset=0;loadApplications().catch(error=>showMessage(error.message,true));});
  $('#previous-page').addEventListener('click',()=>{state.offset=Math.max(0,state.offset-50);loadApplications().catch(error=>showMessage(error.message,true));});
  $('#next-page').addEventListener('click',()=>{state.offset+=50;loadApplications().catch(error=>showMessage(error.message,true));});
  $('#planner-form').addEventListener('input',()=>{state.drafts=[];$('#plan-preview').hidden=true;$('#confirm-plan').hidden=true;});
  $('#planner-form').addEventListener('submit',async event=>{
    event.preventDefault();const button=event.currentTarget.querySelector('button');button.disabled=true;
    const data=Object.fromEntries(new FormData(event.currentTarget));data.duration=Number(data.duration);data.breakMinutes=Number(data.breakMinutes);
    try {
      const result=await api('planner','POST',data);state.drafts=result.drafts;
      const preview=$('#plan-preview');preview.replaceChildren(el('h3',{},'Interview preview'));preview.hidden=false;
      if(!result.drafts.length)preview.append(el('p',{},'No slots prepared. Check your shortlist, role filter and available time window.'));
      else {
        const list=el('ol');
        for(const item of result.drafts)list.append(el('li',{},item.localStart.replace('T',' · ')+' — '+item.name+' — '+roleName(item.roleId)+' · '+item.duration+' min'));
        preview.append(list);
      }
      if(result.skipped.length)preview.append(el('p',{class:'skipped'},'Not scheduled: '+result.skipped.map(item=>item.name+' — '+item.reason).join('; ')));
      $('#confirm-plan').hidden=!result.drafts.length;showMessage('Preview ready. Check the names and slots before confirming.');
    }catch(error){showMessage(error.message,true);}finally{button.disabled=false;}
  });
  $('#confirm-plan').addEventListener('click',async event=>{
    const button=event.currentTarget;button.disabled=true;
    try {const result=await api('interviews','POST',{interviews:state.drafts});state.drafts=[];$('#plan-preview').hidden=true;button.hidden=true;await refresh();showMessage(result.created.length+' interviews saved. The calendar export is ready.');}
    catch(error){showMessage(error.message,true);}finally{button.disabled=false;}
  });
  $('#settings-form').addEventListener('submit',async event=>{
    event.preventDefault();const form=event.currentTarget,button=form.querySelector('button');button.disabled=true;
    const data=Object.fromEntries(new FormData(form));data.smtp_port=Number(data.smtp_port);
    try {const saved=await api('settings','POST',data);form.elements.smtp_password.value='';await loadSettings();showMessage(saved.smtp_ready?'Email settings saved. Queued notifications will send automatically when the SMTP connection succeeds.':'Inbox saved. You can connect the SMTP sender later.');}
    catch(error){showMessage(error.message,true);}finally{button.disabled=false;}
  });
  $('#settings-form [name=smtp_security]').addEventListener('change',event=>{
    const port=$('#settings-form [name=smtp_port]');
    if(event.target.value==='ssl'&&port.value==='587')port.value='465';
    if(event.target.value==='starttls'&&port.value==='465')port.value='587';
  });
  for(const [selector,route,message] of [['#test-email','email-test','Test email queued. Use Refresh to check delivery.'],['#retry-email','email-retry','Failed notifications queued for another attempt.']]){
    $(selector).addEventListener('click',async event=>{const button=event.currentTarget;button.disabled=true;try{await api(route,'POST',{});await loadSettings();showMessage(message);}catch(error){showMessage(error.message,true);}finally{button.disabled=false;}});
  }
  async function start(){
    try {
      const response=await fetch('../site/data/committee-roles.json');if(!response.ok)throw new Error('Role information could not be loaded.');state.meta=await response.json();
      for(const selector of ['#filters [name=role]','#planner-form [name=roleId]'])for(const role of state.meta.roles)$(selector).append(el('option',{value:role.id},role.name));
      $('#planner-form [name=localStart]').value=tomorrow('10:00');$('#planner-form [name=localEnd]').value=tomorrow('13:00');
      await api('session');await signedIn();
    }catch(error){if(error.status!==401)$('#login-message').textContent=error.message;}
  }
  start();
})();
