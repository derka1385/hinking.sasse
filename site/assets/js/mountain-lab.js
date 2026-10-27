/* Local mountain study. One real elevation field, one mesh, no appended cone.
   All shaders and assets are local. No CDN or framework required. */
(() => {
  'use strict';
  const canvas = document.querySelector('#landscape');
  const status = document.querySelector('#status');
  const slider = document.querySelector('#ascent');
  const output = document.querySelector('#distance');
  const weatherButton = document.querySelector('#weather');
  const exploreButton = document.querySelector('#explore');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const coarse = matchMedia('(pointer: coarse)').matches;
  const gl = canvas.getContext('webgl2', {alpha:false, antialias:true, powerPreference:'high-performance'});
  if (!gl) { status.textContent = 'La vue 3D nécessite WebGL 2. Une photographie est affichée à la place.'; return; }
  const clamp = (x,a,b) => Math.max(a,Math.min(b,x));
  const mix = (a,b,t) => a+(b-a)*t;
  const sub = (a,b) => a.map((v,i)=>v-b[i]);
  const cross = (a,b) => [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
  const dot = (a,b) => a.reduce((s,v,i)=>s+v*b[i],0);
  const norm = a => {const l=Math.hypot(...a);return a.map(v=>v/l);};
  const mult = (a,b) => {const o=new Float32Array(16);for(let c=0;c<4;c++)for(let r=0;r<4;r++)for(let k=0;k<4;k++)o[c*4+r]+=a[k*4+r]*b[c*4+k];return o;};
  function lookAt(eye,target,up=[0,1,0]) {
    const z=norm(sub(eye,target)),x=norm(cross(up,z)),y=cross(z,x);
    return new Float32Array([x[0],y[0],z[0],0,x[1],y[1],z[1],0,x[2],y[2],z[2],0,-dot(x,eye),-dot(y,eye),-dot(z,eye),1]);
  }
  function perspective(fov,aspect,n=.04,f=65) {const t=1/Math.tan(fov/2);return new Float32Array([t/aspect,0,0,0,0,t,0,0,0,0,(f+n)/(n-f),-1,0,0,2*f*n/(n-f),0]);}
  function ortho(l,r,b,t,n,f) {return new Float32Array([2/(r-l),0,0,0,0,2/(t-b),0,0,0,0,-2/(f-n),0,-(r+l)/(r-l),-(t+b)/(t-b),-(f+n)/(f-n),1]);}
  function program(vs,fs) {
    const p=gl.createProgram();
    for(const [type,src] of [[gl.VERTEX_SHADER,vs],[gl.FRAGMENT_SHADER,fs]]) {
      const shader=gl.createShader(type);gl.shaderSource(shader,src);gl.compileShader(shader);
      if(!gl.getShaderParameter(shader,gl.COMPILE_STATUS))throw new Error(gl.getShaderInfoLog(shader));
      gl.attachShader(p,shader);gl.deleteShader(shader);
    }
    gl.linkProgram(p);if(!gl.getProgramParameter(p,gl.LINK_STATUS))throw new Error(gl.getProgramInfoLog(p));
    return {p,u:new Proxy({}, {get:(_,name)=>gl.getUniformLocation(p,name)})};
  }
  const fullscreenVS=`#version 300 es
    out vec2 uv;
    void main(){vec2 p=vec2((gl_VertexID<<1)&2,gl_VertexID&2);uv=p;gl_Position=vec4(p*2.-1.,0.,1.);}`;
  const noise=`
    float hash(vec3 p){p=fract(p*.1031);p+=dot(p,p.zyx+31.32);return fract((p.x+p.y)*p.z);}
    float n3(vec3 p){vec3 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);return mix(mix(mix(hash(i),hash(i+vec3(1,0,0)),f.x),mix(hash(i+vec3(0,1,0)),hash(i+vec3(1,1,0)),f.x),f.y),mix(mix(hash(i+vec3(0,0,1)),hash(i+vec3(1,0,1)),f.x),mix(hash(i+vec3(0,1,1)),hash(i+vec3(1,1,1)),f.x),f.y),f.z);}
    float fbm(vec3 p){return n3(p)*.57+n3(p*2.03+9.7)*.28+n3(p*4.07+3.1)*.15;}
  `;
  const terrainVS=`#version 300 es
    layout(location=0)in vec3 position;layout(location=1)in vec3 normal;layout(location=2)in float concavity;
    uniform mat4 vp,lightVP;out vec3 P,N;out float C;out vec4 shadowPosition;
    void main(){P=position;N=normal;C=concavity;shadowPosition=lightVP*vec4(position,1.);gl_Position=vp*vec4(position,1.);}`;
  const terrainFS=`#version 300 es
    precision highp float;
    in vec3 P,N;in float C;in vec4 shadowPosition;out vec4 color;
    uniform sampler2D rockTexture,shadowMap;uniform vec3 camera,sun;uniform float shadowPixel;
    ${noise}
    float shadow(vec3 n){vec3 q=shadowPosition.xyz/shadowPosition.w*.5+.5;
      if(any(lessThan(q,vec3(0.)))||any(greaterThan(q,vec3(1.))))return 1.;
      float bias=.00045+.0012*(1.-max(dot(n,sun),0.)),s=0.;
      for(int y=-1;y<=1;y++)for(int x=-1;x<=1;x++)s+=step(q.z-bias,texture(shadowMap,q.xy+vec2(x,y)*shadowPixel).r);
      return s/9.;}
    vec3 tri(vec3 p,vec3 w){return texture(rockTexture,p.yz).rgb*w.x+texture(rockTexture,p.xz).rgb*w.y+texture(rockTexture,p.xy).rgb*w.z;}
    void main(){
      vec3 ng=normalize(N),weights=pow(abs(ng),vec3(5.));weights/=dot(weights,vec3(1.));
      vec3 rock=tri(P*.85,weights),micro=tri(P*8.5,weights);
      float tex=dot(rock,vec3(.299,.587,.114)),grain=dot(micro,vec3(.299,.587,.114));
      float broad=fbm(P*2.3+vec3(4.,.5,9.));
      // Texture follows strata; snow follows slope and elevation, never a stripe
      // pasted across the face. Concave couloirs retain more snow than aretes.
      float bedding=sin((P.y*.83+P.x*.2-P.z*.27+fbm(P*3.5)*.08)*190.);
      float snowline=smoothstep(1.05,2.1,P.y+broad*.32);
      float summitSnow=smoothstep(2.72,3.3,P.y+broad*.10);
      float threshold=mix(.95,.83,snowline)-summitSnow*.16+.08*(broad-.5)-.055*C;
      float snow=smoothstep(threshold-.055,threshold+.065,ng.y);
      snow*=smoothstep(.5,1.35,P.y+broad*.30);
      float exposed=1.-smoothstep(.27,.62,ng.y);
      float streak=n3(vec3(P.x*75.,P.y*9.,P.z*75.));
      float ribs=pow(1.-abs(2.*fbm(vec3(P.x*28.,P.y*3.,P.z*28.))-1.),3.);
      snow=clamp(snow + snowline*exposed*smoothstep(.70,.88,streak)*.28,0.,1.);
      vec3 base=mix(vec3(.07,.09,.12),vec3(.25,.235,.21),tex);
      base*=.52+broad*.65;base*=.64+grain*.30+ribs*.20+bedding*.025;
      base=mix(base,vec3(.81,.86,.88)*(.97+grain*.06),snow);
      // A surface-gradient normal perturbs fine rock without changing silhouette.
      float h=(tex*.00028+grain*.000028+bedding*.000035+ribs*.008)*(1.-snow*.9);
      vec3 dx=dFdx(P),dy=dFdy(P),r1=cross(dy,ng),r2=cross(ng,dx);
      float det=dot(dx,r1);vec3 sn=normalize(abs(det)*ng-sign(det)*(dFdx(h)*r1+dFdy(h)*r2));
      sn=normalize(mix(ng,sn,.55));
      float dif=max(dot(sn,sun),0.),sh=shadow(ng);
      float ao=1.-max(C,0.)*.20;
      vec3 light=vec3(.29,.39,.53)*(.22+.22*max(ng.y,0.))*ao;
      light+=vec3(1.85,1.62,1.36)*dif*mix(.07,1.,sh);
      vec3 col=base*light;
      vec3 view=normalize(camera-P),halfway=normalize(sun+view);
      col+=vec3(.38,.40,.40)*pow(max(dot(sn,halfway),0.),48.)*snow*.12*sh;
      float d=length(camera-P),heightFog=exp(-max(P.y,0.)*.17);
      float fog=1.-exp(-d*.006*heightFog-d*d*.00012);
      col=mix(col,vec3(.35,.46,.59),fog);
      col=vec3(1.)-exp(-col*1.38);
      color=vec4(pow(col,vec3(1./2.2)),1.);
    }`;
  const skyFS=`#version 300 es
    precision highp float;in vec2 uv;out vec4 color;uniform vec2 resolution;uniform float time,yaw,pitch,motion;
    ${noise}
    void main(){vec2 p=uv;vec2 q=(p-.5)*vec2(resolution.x/resolution.y,1.);
      vec3 col=mix(vec3(.53,.63,.74),vec3(.17,.31,.47),smoothstep(.15,1.,p.y));
      vec3 cloudp=vec3(q.x*2.2+yaw*.6+time*.004*motion,q.y*3.2-pitch*1.6,2.9);
      float c=fbm(cloudp);float cloud=smoothstep(.47,.76,c)*smoothstep(.2,.7,p.y);
      col=mix(col,vec3(.80,.80,.77),cloud*.52);
      float glow=exp(-length(q-vec2(-.67,.22))*2.8);col+=vec3(.20,.14,.075)*glow;
      color=vec4(col,1.);}`;
  const depthVS=`#version 300 es
    layout(location=0)in vec3 position;uniform mat4 lightVP;void main(){gl_Position=lightVP*vec4(position,1.);}`;
  const depthFS=`#version 300 es
    precision highp float;void main(){}`;
  const snowVS=`#version 300 es
    precision highp float;layout(location=0)in vec4 seed;uniform float time,aspect;out float opacity;
    void main(){float z=seed.z;float x=fract(seed.x+time*(.002+.008*z)+sin(time*.25+seed.w)*.018);
      float y=fract(seed.y-time*(.018+.045*z));gl_Position=vec4((x*2.-1.)*1.12,(y*2.-1.)*1.1,0.,1.);
      gl_PointSize=mix(.8,2.7,z);opacity=mix(.08,.36,z);}`;
  const snowFS=`#version 300 es
    precision highp float;in float opacity;out vec4 color;void main(){float d=length(gl_PointCoord-.5);float a=(1.-smoothstep(.08,.5,d))*opacity;color=vec4(.9,.94,1.,a);}`;

  let terrain,sky,depth,snow,mesh,shadowTexture,shadowFbo,rockTexture,meta,data;
  let indicesCount=0,ready=false,raf=0,lastTime=0,lastDraw=0,elapsed=0,measured=0,frameSamples=0;
  let width=0,height=0,pixelScale=coarse?1:1.4;
  const SUN=norm([-.85,.42,-.18]);
  const lightEye=SUN.map((v,i)=>v*22+(i===1?2.5:0));
  const lightVP=mult(ortho(-13,13,-13,13,.1,55),lookAt(lightEye,[0,2.5,0]));
  let weather=!reduced.matches,playing=false,dragging=false,lastPointer=null;
  let desired={yaw:-1.15,pitch:.045,progress:.36},current={...desired};
  const stats={triangles:0,frames:0,cpuSubmissionMs:0,renderScale:pixelScale,webgl:'WebGL 2',source:'Copernicus DEM GLO-30'};
  let gpuSnow,snowCount=coarse?100:210;

  function syncWeather(){weatherButton.setAttribute('aria-pressed',String(weather));weatherButton.querySelector('span').textContent=weather?'On':'Off';}
  syncWeather();
  function stopTour(){playing=false;exploreButton.setAttribute('aria-pressed','false');exploreButton.firstChild.textContent='Parcourir ';}
  function updateProgress(v){desired.progress=clamp(v,0,1);slider.value=String(desired.progress*100);output.value=desired.progress>.77?'Près de la face':desired.progress<.12?'Vue large':'Approche';}
  function reset(){stopTour();desired={yaw:-1.15,pitch:.045,progress:.36};updateProgress(.36);wake();}
  document.querySelector('#reset').addEventListener('click',reset);
  weatherButton.addEventListener('click',()=>{weather=!weather;syncWeather();wake();});
  slider.addEventListener('input',()=>{stopTour();updateProgress(Number(slider.value)/100);wake();});
  exploreButton.addEventListener('click',()=>{playing=!playing;exploreButton.setAttribute('aria-pressed',String(playing));exploreButton.firstChild.textContent=playing?'Pause ':'Parcourir ';wake();});
  canvas.addEventListener('wheel',e=>{e.preventDefault();stopTour();updateProgress(desired.progress+clamp(e.deltaY,-100,100)*.00065);wake();},{passive:false});
  canvas.addEventListener('pointerdown',e=>{stopTour();dragging=true;lastPointer=[e.clientX,e.clientY];canvas.setPointerCapture(e.pointerId);canvas.focus({preventScroll:true});wake();});
  canvas.addEventListener('pointermove',e=>{if(!dragging)return;desired.yaw-=(e.clientX-lastPointer[0])*.004;desired.pitch=clamp(desired.pitch+(e.clientY-lastPointer[1])*.002,-.02,.50);lastPointer=[e.clientX,e.clientY];wake();});
  const endDrag=()=>{dragging=false;lastPointer=null;};
  canvas.addEventListener('pointerup',endDrag);canvas.addEventListener('pointercancel',endDrag);canvas.addEventListener('lostpointercapture',endDrag);
  canvas.addEventListener('keydown',e=>{const moves={ArrowLeft:[-.06,0],ArrowRight:[.06,0],ArrowUp:[0,.025],ArrowDown:[0,-.025]};if(moves[e.key]){e.preventDefault();stopTour();desired.yaw+=moves[e.key][0];desired.pitch=clamp(desired.pitch+moves[e.key][1],-.02,.50);wake();}else if(e.key==='+'||e.key==='='){updateProgress(desired.progress+.04);wake();}else if(e.key==='-'){updateProgress(desired.progress-.04);wake();}else if(e.key.toLowerCase()==='r'){reset();}});
  reduced.addEventListener('change',()=>{weather=!reduced.matches;stopTour();syncWeather();wake();});
  document.addEventListener('visibilitychange',()=>{if(document.hidden){cancelAnimationFrame(raf);raf=0;lastTime=0;}else wake();});
  addEventListener('pagehide',()=>{cancelAnimationFrame(raf);raf=0;});
  canvas.addEventListener('webglcontextlost',e=>{e.preventDefault();ready=false;cancelAnimationFrame(raf);raf=0;status.textContent='La vue 3D a été interrompue. Recharge la page pour la relancer.';});
  canvas.addEventListener('webglcontextrestored',()=>location.reload());

  function resize(){
    const cap=coarse?1400000:2400000;
    const dpr=Math.min(devicePixelRatio||1,pixelScale,Math.sqrt(cap/(canvas.clientWidth*canvas.clientHeight)));
    width=Math.max(1,Math.round(canvas.clientWidth*dpr));height=Math.max(1,Math.round(canvas.clientHeight*dpr));
    if(canvas.width!==width||canvas.height!==height){canvas.width=width;canvas.height=height;}
    stats.renderScale=dpr;
  }
  new ResizeObserver(()=>{resize();wake();}).observe(canvas);
  function heightAt(x,z){
    const locate=(a,v)=>{let lo=0,hi=a.length-1;while(hi-lo>1){const m=(lo+hi)>>1;if(a[m]>v)hi=m;else lo=m;}return[lo,clamp((v-a[lo])/(a[lo+1]-a[lo]),0,1)];};
    const [ix,fx]=locate(meta.x,x),[iz,fz]=locate(meta.z,z),w=meta.columns;
    const h=(r,c)=>data[(r*w+c)*7+1];return mix(mix(h(iz,ix),h(iz,ix+1),fx),mix(h(iz+1,ix),h(iz+1,ix+1),fx),fz);
  }
  function cameraAt(){
    const p=current.progress,r=mix(12.4,3.05,p),y=mix(1.52,2.68,p);
    const target=[-.05,y,-.05],breathe=reduced.matches?0:Math.sin(elapsed*.21)*.0012;
    const eye=[target[0]+Math.sin(current.yaw+breathe)*r, y+Math.sin(current.pitch)*r,target[2]+Math.cos(current.yaw+breathe)*r];
    eye[1]=Math.max(eye[1],heightAt(eye[0],eye[2])+.23);
    return{eye,target,vp:mult(perspective(.69,width/height),lookAt(eye,target))};
  }
  function draw(){
    const {eye,vp}=cameraAt();
    gl.bindFramebuffer(gl.FRAMEBUFFER,null);gl.viewport(0,0,width,height);gl.disable(gl.DEPTH_TEST);gl.disable(gl.BLEND);gl.bindVertexArray(null);
    gl.useProgram(sky.p);gl.uniform2f(sky.u.resolution,width,height);gl.uniform1f(sky.u.time,elapsed);gl.uniform1f(sky.u.yaw,current.yaw);gl.uniform1f(sky.u.pitch,current.pitch);gl.uniform1f(sky.u.motion,reduced.matches?0:1);gl.drawArrays(gl.TRIANGLES,0,3);
    gl.clear(gl.DEPTH_BUFFER_BIT);gl.enable(gl.DEPTH_TEST);gl.useProgram(terrain.p);gl.bindVertexArray(mesh);
    gl.uniformMatrix4fv(terrain.u.vp,false,vp);gl.uniformMatrix4fv(terrain.u.lightVP,false,lightVP);gl.uniform3fv(terrain.u.camera,eye);gl.uniform3fv(terrain.u.sun,SUN);gl.uniform1f(terrain.u.shadowPixel,1/(coarse?1024:2048));
    gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,rockTexture);gl.uniform1i(terrain.u.rockTexture,0);
    gl.activeTexture(gl.TEXTURE1);gl.bindTexture(gl.TEXTURE_2D,shadowTexture);gl.uniform1i(terrain.u.shadowMap,1);gl.drawElements(gl.TRIANGLES,indicesCount,gl.UNSIGNED_INT,0);
    if(weather){gl.disable(gl.DEPTH_TEST);gl.enable(gl.BLEND);gl.blendFunc(gl.SRC_ALPHA,gl.ONE_MINUS_SRC_ALPHA);gl.useProgram(snow.p);gl.bindVertexArray(gpuSnow);gl.uniform1f(snow.u.time,elapsed);gl.uniform1f(snow.u.aspect,width/height);gl.drawArrays(gl.POINTS,0,snowCount);gl.disable(gl.BLEND);}
    stats.frames++;stats.camera=eye.map(v=>Math.round(v*1000));stats.progress=Number(current.progress.toFixed(3));
    if(stats.frames%30===0)canvas.dataset.renderStats=JSON.stringify(stats);
  }
  function frame(now){
    raf=0;if(!ready||document.hidden)return;
    const dt=lastTime?Math.min((now-lastTime)/1000,.05):1/60;lastTime=now;elapsed+=dt;
    if(playing){updateProgress(desired.progress+dt*.022);desired.yaw+=dt*.025;if(desired.progress>=.94)stopTour();}
    const moving=Math.abs(desired.yaw-current.yaw)+Math.abs(desired.pitch-current.pitch)+Math.abs(desired.progress-current.progress)>.0002;
    const f=1-Math.exp(-dt*9);for(const k of ['yaw','pitch','progress'])current[k]=mix(current[k],desired[k],f);
    if(now-lastDraw>=(moving||dragging||playing?14:32)){
      const start=performance.now();draw();const duration=performance.now()-start;
      measured+=duration;frameSamples++;stats.cpuSubmissionMs=Math.round(measured/frameSamples*100)/100;
      // Cap resolution once a sustained CPU/GPU scheduling cost is observed.
      if(frameSamples===60&&stats.cpuSubmissionMs>18&&pixelScale>1){pixelScale=1;resize();}
      lastDraw=now;
    }
    if(moving||playing||weather||!reduced.matches)wake();
  }
  function wake(){if(ready&&!document.hidden&&!raf)raf=requestAnimationFrame(frame);}
  window.mountainPreview={stats,reset,setProgress:p=>{updateProgress(p);wake();},getCamera:()=>ready?cameraAt().eye:null};

  async function init(){
    for(const b of [weatherButton,exploreButton,document.querySelector('#reset'),slider])b.disabled=true;
    try {
      terrain=program(terrainVS,terrainFS);sky=program(fullscreenVS,skyFS);depth=program(depthVS,depthFS);snow=program(snowVS,snowFS);
      const [manifest,binary,image]=await Promise.all([
        fetch('assets/mountain/khumbu.json').then(r=>{if(!r.ok)throw new Error('Relief indisponible');return r.json();}),
        fetch('assets/mountain/khumbu.bin').then(r=>{if(!r.ok)throw new Error('Relief indisponible');return r.arrayBuffer();}),
        new Promise((resolve,reject)=>{const i=new Image();i.onload=()=>resolve(i);i.onerror=()=>reject(new Error('Texture indisponible'));i.src='assets/img/intro-kebnekaise-rock.webp';})
      ]);
      meta=manifest;const packed=new DataView(binary);const {columns:w,rows:h}=meta;
      if(binary.byteLength!==w*h*8)throw new Error('Données de relief incomplètes');
      data=new Float32Array(w*h*7);
      for(let j=0;j<h;j++)for(let i=0;i<w;i++){
        const k=j*w+i,o=k*7,b=k*8,nx=packed.getInt16(b+2,true)/32767,nz=packed.getInt16(b+4,true)/32767;
        data[o]=meta.x[i];data[o+1]=(packed.getUint16(b,true)/7-3400)/1000;data[o+2]=meta.z[j];data[o+3]=nx;data[o+4]=Math.sqrt(Math.max(0,1-nx*nx-nz*nz));data[o+5]=nz;data[o+6]=packed.getInt16(b+6,true)/32767;
      }
      const step=coarse?2:1,rows=[],cols=[];
      for(let j=0;j<h-1;j+=step)rows.push(j);rows.push(h-1);for(let i=0;i<w-1;i+=step)cols.push(i);cols.push(w-1);
      const indices=new Uint32Array((rows.length-1)*(cols.length-1)*6);let q=0;
      for(let j=0;j<rows.length-1;j++)for(let i=0;i<cols.length-1;i++){
        const a=rows[j]*w+cols[i],b=rows[j]*w+cols[i+1],c=rows[j+1]*w+cols[i],d=rows[j+1]*w+cols[i+1];
        indices[q++]=a;indices[q++]=c;indices[q++]=b;indices[q++]=b;indices[q++]=c;indices[q++]=d;
      }
      indicesCount=indices.length;stats.triangles=indicesCount/3;
      mesh=gl.createVertexArray();gl.bindVertexArray(mesh);
      const vb=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,vb);gl.bufferData(gl.ARRAY_BUFFER,data,gl.STATIC_DRAW);
      for(const [loc,n,off]of[[0,3,0],[1,3,12],[2,1,24]]){gl.enableVertexAttribArray(loc);gl.vertexAttribPointer(loc,n,gl.FLOAT,false,28,off);}
      const ib=gl.createBuffer();gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,ib);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,indices,gl.STATIC_DRAW);
      rockTexture=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,rockTexture);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGB,gl.RGB,gl.UNSIGNED_BYTE,image);gl.generateMipmap(gl.TEXTURE_2D);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR_MIPMAP_LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.REPEAT);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.REPEAT);
      const ext=gl.getExtension('EXT_texture_filter_anisotropic');if(ext)gl.texParameterf(gl.TEXTURE_2D,ext.TEXTURE_MAX_ANISOTROPY_EXT,Math.min(8,gl.getParameter(ext.MAX_TEXTURE_MAX_ANISOTROPY_EXT)));
      const size=coarse?1024:2048;
      shadowTexture=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,shadowTexture);gl.texImage2D(gl.TEXTURE_2D,0,gl.DEPTH_COMPONENT24,size,size,0,gl.DEPTH_COMPONENT,gl.UNSIGNED_INT,null);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.NEAREST);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.NEAREST);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);
      shadowFbo=gl.createFramebuffer();gl.bindFramebuffer(gl.FRAMEBUFFER,shadowFbo);gl.framebufferTexture2D(gl.FRAMEBUFFER,gl.DEPTH_ATTACHMENT,gl.TEXTURE_2D,shadowTexture,0);gl.drawBuffers([gl.NONE]);gl.readBuffer(gl.NONE);
      if(gl.checkFramebufferStatus(gl.FRAMEBUFFER)!==gl.FRAMEBUFFER_COMPLETE)throw new Error('Éclairage indisponible sur cet appareil');
      gl.viewport(0,0,size,size);gl.enable(gl.DEPTH_TEST);gl.clear(gl.DEPTH_BUFFER_BIT);gl.useProgram(depth.p);gl.uniformMatrix4fv(depth.u.lightVP,false,lightVP);gl.enable(gl.POLYGON_OFFSET_FILL);gl.polygonOffset(1.1,2);gl.drawElements(gl.TRIANGLES,indicesCount,gl.UNSIGNED_INT,0);gl.disable(gl.POLYGON_OFFSET_FILL);
      // Static lighting: the shadow map is generated once, not every animation frame.
      const seeds=new Float32Array(snowCount*4);let seed=41;const random=()=>{seed=(seed*1664525+1013904223)>>>0;return seed/4294967296;};for(let i=0;i<seeds.length;i++)seeds[i]=random();
      gpuSnow=gl.createVertexArray();gl.bindVertexArray(gpuSnow);const sb=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,sb);gl.bufferData(gl.ARRAY_BUFFER,seeds,gl.STATIC_DRAW);gl.enableVertexAttribArray(0);gl.vertexAttribPointer(0,4,gl.FLOAT,false,16,0);
      gl.bindFramebuffer(gl.FRAMEBUFFER,null);gl.bindVertexArray(null);resize();ready=true;draw();document.body.classList.add('ready');status.textContent='';
      for(const b of [weatherButton,exploreButton,document.querySelector('#reset'),slider])b.disabled=false;wake();
    }catch(e){console.error('Mountain preview:',e);status.textContent='La vue 3D n’a pas pu se charger. Recharge la page pour réessayer.';stats.error=e.message;}
  }
  init();
})();
