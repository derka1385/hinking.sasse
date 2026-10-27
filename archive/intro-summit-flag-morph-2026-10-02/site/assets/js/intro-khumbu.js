// The approved mountain-lab mesh. World placement is a uniform scale + rotation
// + translation; packed source data stay intact. Only the close-up summit cells
// gain smooth subdivision and a bounded layer of wind-sculpted snow.
// Render linear material/light and surface distance; intro.js applies the
// published atmosphere, moving volumetric clouds, film curve and snow.
(() => {
  'use strict';
  const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
  const mix=(a,b,t)=>a+(b-a)*t;
  const dot=(a,b)=>a.reduce((s,v,i)=>s+v*b[i],0);
  const norm=a=>{const d=Math.hypot(...a);return a.map(v=>v/d);};
  const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
  function lookAt(eye,target){const z=norm(eye.map((v,i)=>v-target[i])),x=norm(cross([0,1,0],z)),y=cross(z,x);return new Float32Array([x[0],y[0],z[0],0,x[1],y[1],z[1],0,x[2],y[2],z[2],0,-dot(x,eye),-dot(y,eye),-dot(z,eye),1]);}
  function multiply(a,b){const r=new Float32Array(16);for(let c=0;c<4;c++)for(let j=0;j<4;j++)for(let k=0;k<4;k++)r[c*4+j]+=a[k*4+j]*b[c*4+k];return r;}
  const ortho=(size,near,far)=>new Float32Array([1/size,0,0,0,0,1/size,0,0,0,0,-2/(far-near),0,0,0,-(far+near)/(far-near),1]);
  const VS=`#version 300 es
    layout(location=0) in vec3 position;layout(location=1) in vec3 normal;layout(location=2) in float concavity;
    uniform mat4 vp,model,lightVP;out vec3 P,N,worldP;out float C;out vec4 shadowPosition;
    void main(){P=position;N=normal;C=concavity;worldP=(model*vec4(position,1.)).xyz;shadowPosition=lightVP*vec4(worldP,1.);gl_Position=vp*vec4(worldP,1.);}`;
  const DEPTH_VS=`#version 300 es
    layout(location=0)in vec3 position;uniform mat4 model,lightVP;
    void main(){gl_Position=lightVP*model*vec4(position,1.);}`;
  const DEPTH_FS=`#version 300 es
    precision highp float;void main(){}`;
  // The material below is the approved preview's material, before its former
  // sky/fog/gamma. Its lighting now follows the published intro's exact equation.
  const FS=`#version 300 es
    precision highp float;
    in vec3 P,N,worldP;in float C;in vec4 shadowPosition;
    layout(location=0)out vec4 color;layout(location=1)out vec4 distanceColor;
    uniform sampler2D rockTexture;uniform highp sampler2DShadow shadowMap;uniform vec3 camera,sun,sunCol,fogCol;
    uniform mat3 rotation;uniform float shadowPixel;uniform vec3 summit;
    float hash(vec3 p){p=fract(p*.1031);p+=dot(p,p.zyx+31.32);return fract((p.x+p.y)*p.z);}
    float rawNoise(vec3 p){vec3 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);return mix(mix(mix(hash(i),hash(i+vec3(1,0,0)),f.x),mix(hash(i+vec3(0,1,0)),hash(i+vec3(1,1,0)),f.x),f.y),mix(mix(hash(i+vec3(0,0,1)),hash(i+vec3(1,0,1)),f.x),mix(hash(i+vec3(0,1,1)),hash(i+vec3(1,1,1)),f.x),f.y),f.z);}
    // Fade unresolved procedural octaves to their mean before they can alias.
    // The footprint follows the surface in world space, so it changes continuously.
    float n3(vec3 p){vec3 footprint=max(abs(dFdx(p)),abs(dFdy(p)));float f=max(footprint.x,max(footprint.y,footprint.z));return mix(rawNoise(p),.5,smoothstep(.35,.90,f));}
    float fbm(vec3 p){return n3(p)*.57+n3(p*2.03+9.7)*.28+n3(p*4.07+3.1)*.15;}
    float shadow(vec3 n){vec3 q=shadowPosition.xyz/shadowPosition.w*.5+.5;if(any(lessThan(q,vec3(0.)))||any(greaterThan(q,vec3(1.))))return 1.;float bias=.00018+.00042*(1.-max(dot(n,sun),0.)),s=0.;for(int y=-1;y<=1;y++)for(int x=-1;x<=1;x++)s+=texture(shadowMap,vec3(q.xy+vec2(x,y)*shadowPixel,q.z-bias));return s/9.;}
    vec3 tri(vec3 p,vec3 w){return texture(rockTexture,p.yz).rgb*w.x+texture(rockTexture,p.xz).rgb*w.y+texture(rockTexture,p.xy).rgb*w.z;}
    vec3 packDistance(float v){vec3 e=fract(v*vec3(1.,255.,65025.));e-=e.yzz*vec3(1./255.,1./255.,0.);return e;}
    void main(){
      vec3 ng=normalize(N),weights=pow(abs(ng),vec3(5.));weights/=dot(weights,vec3(1.));
      vec3 rock=tri(P*.85,weights),micro=tri(P*8.5,weights);
      float tex=dot(rock,vec3(.299,.587,.114)),grain=dot(micro,vec3(.299,.587,.114));
      float broad=fbm(P*2.3+vec3(4.,.5,9.));
      float bedPhase=(P.y*.83+P.x*.2-P.z*.27+fbm(P*3.5)*.08)*190.;
      float bedding=sin(bedPhase)*(1.-smoothstep(1.5,4.,fwidth(bedPhase)));
      float snowline=smoothstep(1.05,2.1,P.y+broad*.32);
      float summitSnow=smoothstep(2.72,3.3,P.y+broad*.10);
      float threshold=mix(.95,.83,snowline)-summitSnow*.16+.08*(broad-.5)-.055*C;
      float edge=fwidth(ng.y)*.5;
      float snow=smoothstep(threshold-.055-edge,threshold+.065+edge,ng.y);
      snow*=smoothstep(.5,1.35,P.y+broad*.30);
      float exposed=1.-smoothstep(.27,.62,ng.y);
      float streak=n3(vec3(P.x*75.,P.y*9.,P.z*75.));
      float ribs=pow(1.-abs(2.*fbm(vec3(P.x*28.,P.y*3.,P.z*28.))-1.),3.);
      snow=clamp(snow+snowline*exposed*smoothstep(.70,.88,streak)*.28,0.,1.);
      vec3 base=mix(vec3(.07,.09,.12),vec3(.25,.235,.21),tex);
      base*=.52+broad*.65;base*=.64+grain*.30+ribs*.20+bedding*.025;
      base=mix(base,vec3(.81,.86,.88)*(.97+grain*.06),snow);
      float closeSummit=1.-smoothstep(.12,.19,length(P.xz-summit.xz));
      vec3 metres=P*1000.;
      float driftPhase=metres.x*.85+metres.z*.20+fbm(P*90.)*5.;
      float windRidges=sin(driftPhase)*(1.-smoothstep(1.5,4.,fwidth(driftPhase)));
      float crystals=n3(metres*7.5),packed=n3(metres*.35);
      base*=1.-snow*closeSummit*(.07*(1.-windRidges)+.055*(1.-packed));
      float snowRelief=snow*closeSummit*(windRidges*.00013+(packed-.5)*.00010+(crystals-.5)*.000008);
      float h=snowRelief+(tex*.00028+grain*.000028+bedding*.000035+ribs*.008)*(1.-snow*.9);
      vec3 dx=dFdx(P),dy=dFdy(P),r1=cross(dy,ng),r2=cross(ng,dx);
      float det=dot(dx,r1);
      vec3 gradient=(dFdx(h)*r1+dFdy(h)*r2)/(abs(det)>1e-10?det:1e-10);
      gradient-=ng*dot(ng,gradient);
      gradient*=min(1.,.6/max(length(gradient),.001));
      float detail=1.-smoothstep(.002,.012,max(length(dx),length(dy)));
      vec3 sn=normalize(ng-gradient*detail);
      sn=normalize(rotation*normalize(mix(ng,sn,.55)));
      vec3 worldN=normalize(rotation*ng);
      float dif=max(dot(sn,sun),0.),occ=1.-max(C,0.)*.20,sh=shadow(worldN);
      // Published 595da57 shade(): direct sun, sky, snow bounce, specular.
      vec3 sky=fogCol*2.2+vec3(.02,.03,.05);
      vec3 lin=sunCol*dif*sh
             +sky*(.55+.45*worldN.y)*occ
             +fogCol*1.4*(.5-.5*worldN.y)*occ;
      vec3 rd=normalize(worldP-camera);
      vec3 col=base*lin;
      col+=snow*.03*sunCol*pow(max(dot(reflect(rd,sn),sun),0.),8.)*sh;
      // Square-root HDR encoding in RGBA8: works without float render targets.
      color=vec4(sqrt(clamp(col/4.,0.,1.)),1.);
      distanceColor=vec4(packDistance(min(length(worldP-camera)/20000.,.999999)),1.);
    }`;

  async function load(base='site/assets/mountain/'){
    const checked=async url=>{const r=await fetch(url);if(!r.ok)throw new Error('Mountain asset unavailable: '+url);return r;};
    const [meta,bytes]=await Promise.all([checked(base+'khumbu.json').then(r=>r.json()),checked(base+'khumbu.bin').then(r=>r.arrayBuffer())]);
    const {rows,columns}=meta;
    if(meta.encoding!=='height7-normalxz-concavity-i16'||bytes.byteLength!==rows*columns*8)throw new Error('Invalid mountain data');
    const packed=new DataView(bytes),data=new Float32Array(rows*columns*7);let peak=[0,-Infinity,0];
    for(let j=0;j<rows;j++)for(let i=0;i<columns;i++){
      const k=j*columns+i,b=k*8,o=k*7,nx=packed.getInt16(b+2,true)/32767,nz=packed.getInt16(b+4,true)/32767;
      const x=meta.x[i],y=(packed.getUint16(b,true)/7-meta.datumMetres)/1000,z=meta.z[j];
      data.set([x,y,z,nx,Math.sqrt(Math.max(0,1-nx*nx-nz*nz)),nz,packed.getInt16(b+6,true)/32767],o);
      if(Math.abs(x)<.8&&Math.abs(z)<.8&&y>peak[1])peak=[x,y,z];
    }
    const locate=(a,v)=>{let lo=0,hi=a.length-1;while(hi-lo>1){const mid=(lo+hi)>>1;if(a[mid]>v)hi=mid;else lo=mid;}return[lo,clamp((v-a[lo])/(a[lo+1]-a[lo]),0,1)];};
    const model={meta,data,peak,transform:null,rotation:null,scale:1000,yaw:.159};
    model.register=(summit,scale=1000,yaw=.159)=>{
      model.scale=scale;model.yaw=yaw;const c=Math.cos(yaw),s=Math.sin(yaw);
      const x=summit[0]-scale*(c*peak[0]+s*peak[2]),y=summit[1]-scale*peak[1],z=summit[2]-scale*(-s*peak[0]+c*peak[2]);
      model.transform=new Float32Array([scale*c,0,-scale*s,0,0,scale,0,0,scale*s,0,scale*c,0,x,y,z,1]);
      model.rotation=new Float32Array([c,0,-s,0,1,0,s,0,c]);
    };
    // Metre-scale detail is confined to the photographed summit. The source DEM
    // remains intact; stitched cell edges and the same sampler keep collisions honest.
    const smooth=t=>t*t*(3-2*t);
    const cubic=(a,b,c,d,t)=>b+.5*t*(c-a+t*(2*a-5*b+4*c-d+t*(3*(b-c)+d-a)));
    const heightLocal=(x,z)=>{
      const [ix,fx]=locate(meta.x,x),[iz,fz]=locate(meta.z,z);
      const h=(r,c)=>data[(clamp(r,0,rows-1)*columns+clamp(c,0,columns-1))*7+1];
      const a=h(iz,ix),b=h(iz,ix+1),c=h(iz+1,ix),d=h(iz+1,ix+1);
      const base=fx+fz<=1?a+(b-a)*fx+(c-a)*fz:d+(c-d)*(1-fx)+(b-d)*(1-fz);
      const radius=Math.hypot(x-peak[0],z-peak[2]);
      const blend=1-smooth(clamp((radius-.14)/.05,0,1));
      if(!blend)return base;
      const q=[];for(let r=-1;r<=2;r++)q.push(cubic(h(iz+r,ix-1),h(iz+r,ix),h(iz+r,ix+1),h(iz+r,ix+2),fx));
      const rounded=Math.min(peak[1],cubic(...q,fz));
      const xm=(x-peak[0])*1000,zm=(z-peak[2])*1000;
      const ripple=(.09*Math.sin(xm*.55+zm*.13+.5*Math.sin(zm*.11))+.035*Math.sin(xm*1.8+zm*.5))*smooth(clamp(radius/.012,0,1));
      return mix(base,rounded+ripple/1000,blend);
    };
    model.heightAt=(x,z)=>{
      const m=model.transform,c=Math.cos(model.yaw),s=Math.sin(model.yaw);
      const wx=(x-m[12])/model.scale,wz=(z-m[14])/model.scale;
      return m[13]+model.scale*heightLocal(c*wx-s*wz,s*wx+c*wz);
    };
    model.summitMesh=coarse=>{
      const step=coarse?2:1,subdivisions=coarse?8:12,rr=[],cc=[],extra=[],idx=[];
      for(let r=0;r<rows-1;r+=step)rr.push(r);rr.push(rows-1);
      for(let c=0;c<columns-1;c+=step)cc.push(c);cc.push(columns-1);
      let refinedCells=0;
      const vertex=(x,z)=>{
        const y=heightLocal(x,z),e=.00025;
        const n=norm([-(heightLocal(x+e,z)-heightLocal(x-e,z))/(2*e),1,-(heightLocal(x,z+e)-heightLocal(x,z-e))/(2*e)]);
        const [c,fx]=locate(meta.x,x),[r,fz]=locate(meta.z,z),at=(r,c)=>data[(r*columns+c)*7+6];
        const concavity=mix(mix(at(r,c),at(r,c+1),fx),mix(at(r+1,c),at(r+1,c+1),fx),fz);
        const i=data.length/7+extra.length/7;extra.push(x,y,z,...n,concavity);return i;
      };
      for(let j=0;j<rr.length-1;j++)for(let i=0;i<cc.length-1;i++){
        const r=rr[j],r1=rr[j+1],c=cc[i],c1=cc[i+1],x0=meta.x[c],x1=meta.x[c1],z0=meta.z[r],z1=meta.z[r1];
        if(Math.abs((x0+x1)/2-peak[0])<.21&&Math.abs((z0+z1)/2-peak[2])<.21){
          refinedCells++;const grid=[];
          for(let y=0;y<=subdivisions;y++)for(let x=0;x<=subdivisions;x++)grid.push(vertex(mix(x0,x1,x/subdivisions),mix(z0,z1,y/subdivisions)));
          for(let y=0;y<subdivisions;y++)for(let x=0;x<subdivisions;x++){
            const a=grid[y*(subdivisions+1)+x],b=grid[y*(subdivisions+1)+x+1],c=grid[(y+1)*(subdivisions+1)+x],d=grid[(y+1)*(subdivisions+1)+x+1];idx.push(a,c,b,b,c,d);
          }
        }else{const a=r*columns+c,b=r*columns+c1,c2=r1*columns+c,d=r1*columns+c1;idx.push(a,c2,b,b,c2,d);}
      }
      const vertices=new Float32Array(data.length+extra.length);vertices.set(data);vertices.set(extra,data.length);
      return {vertices,indices:new Uint32Array(idx),refinedCells};
    };
    model.upload=(gl,program,coarse,rockTex)=>{
      const material=program(VS,FS),depth=program(DEPTH_VS,DEPTH_FS);
      if(!material||!depth)throw new Error('Mountain shaders failed');
      const {vertices,indices,refinedCells}=model.summitMesh(coarse);
      const vao=gl.createVertexArray();gl.bindVertexArray(vao);
      const vb=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,vb);gl.bufferData(gl.ARRAY_BUFFER,vertices,gl.STATIC_DRAW);
      for(const[loc,size,offset]of[[0,3,0],[1,3,12],[2,1,24]]){gl.enableVertexAttribArray(loc);gl.vertexAttribPointer(loc,size,gl.FLOAT,false,28,offset);}
      const ib=gl.createBuffer();gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER,ib);gl.bufferData(gl.ELEMENT_ARRAY_BUFFER,indices,gl.STATIC_DRAW);
      const texture=()=>{const t=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,t);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.NEAREST);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.NEAREST);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);return t;};
      const colorTex=texture(),distanceTex=texture(),fbo=gl.createFramebuffer(),depthBuffer=gl.createRenderbuffer();
      // Resolve MSAA explicitly because the terrain uses an offscreen MRT target.
      // The canvas context's antialias flag cannot smooth this framebuffer.
      const samples=Math.min(coarse?2:4,Number(gl.getParameter(gl.MAX_SAMPLES))||1);
      const aaFbo=samples>1?gl.createFramebuffer():null;
      const aaColor=samples>1?[gl.createRenderbuffer(),gl.createRenderbuffer()]:[];
      const aaDepth=samples>1?gl.createRenderbuffer():null;
      let w=0,h=0,lastSun=null,lightVP=null;
      const shadowSize=coarse?2048:4096,shadowTex=texture(),shadowFbo=gl.createFramebuffer();
      gl.bindTexture(gl.TEXTURE_2D,shadowTex);
      gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_COMPARE_MODE,gl.COMPARE_REF_TO_TEXTURE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_COMPARE_FUNC,gl.LEQUAL);
      gl.texImage2D(gl.TEXTURE_2D,0,gl.DEPTH_COMPONENT24,shadowSize,shadowSize,0,gl.DEPTH_COMPONENT,gl.UNSIGNED_INT,null);
      gl.bindFramebuffer(gl.FRAMEBUFFER,shadowFbo);gl.framebufferTexture2D(gl.FRAMEBUFFER,gl.DEPTH_ATTACHMENT,gl.TEXTURE_2D,shadowTex,0);gl.drawBuffers([gl.NONE]);gl.readBuffer(gl.NONE);
      if(gl.checkFramebufferStatus(gl.FRAMEBUFFER)!==gl.FRAMEBUFFER_COMPLETE)throw new Error('Mountain shadow target incomplete');
      gl.bindFramebuffer(gl.FRAMEBUFFER,null);gl.bindVertexArray(null);
      function resize(W,H){
        if(w===W&&h===H)return;w=W;h=H;gl.bindFramebuffer(gl.FRAMEBUFFER,fbo);
        for(const[t,attachment]of[[colorTex,gl.COLOR_ATTACHMENT0],[distanceTex,gl.COLOR_ATTACHMENT1]]){gl.bindTexture(gl.TEXTURE_2D,t);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA8,w,h,0,gl.RGBA,gl.UNSIGNED_BYTE,null);gl.framebufferTexture2D(gl.FRAMEBUFFER,attachment,gl.TEXTURE_2D,t,0);}
        gl.bindRenderbuffer(gl.RENDERBUFFER,depthBuffer);gl.renderbufferStorage(gl.RENDERBUFFER,gl.DEPTH_COMPONENT24,w,h);gl.framebufferRenderbuffer(gl.FRAMEBUFFER,gl.DEPTH_ATTACHMENT,gl.RENDERBUFFER,depthBuffer);gl.drawBuffers([gl.COLOR_ATTACHMENT0,gl.COLOR_ATTACHMENT1]);
        if(gl.checkFramebufferStatus(gl.FRAMEBUFFER)!==gl.FRAMEBUFFER_COMPLETE)throw new Error('Mountain render target incomplete');
        if(aaFbo){
          gl.bindFramebuffer(gl.FRAMEBUFFER,aaFbo);
          for(let i=0;i<2;i++){gl.bindRenderbuffer(gl.RENDERBUFFER,aaColor[i]);gl.renderbufferStorageMultisample(gl.RENDERBUFFER,samples,gl.RGBA8,w,h);gl.framebufferRenderbuffer(gl.FRAMEBUFFER,gl.COLOR_ATTACHMENT0+i,gl.RENDERBUFFER,aaColor[i]);}
          gl.bindRenderbuffer(gl.RENDERBUFFER,aaDepth);gl.renderbufferStorageMultisample(gl.RENDERBUFFER,samples,gl.DEPTH_COMPONENT24,w,h);gl.framebufferRenderbuffer(gl.FRAMEBUFFER,gl.DEPTH_ATTACHMENT,gl.RENDERBUFFER,aaDepth);gl.drawBuffers([gl.COLOR_ATTACHMENT0,gl.COLOR_ATTACHMENT1]);
          if(gl.checkFramebufferStatus(gl.FRAMEBUFFER)!==gl.FRAMEBUFFER_COMPLETE)throw new Error('Mountain antialias target incomplete');
        }
      }
      function render(vp,camera,L,W,H){
        gl.disable(gl.BLEND);gl.enable(gl.DEPTH_TEST);gl.depthFunc(gl.LESS);gl.depthMask(true);gl.bindVertexArray(vao);
        if(!lastSun||Math.hypot(...L.sunDir.map((v,i)=>v-lastSun[i]))>1e-5){
          const centre=[80,850,-345],eye=L.sunDir.map((v,i)=>centre[i]+v*15000);
          lightVP=multiply(ortho(6500,.1,30000),lookAt(eye,centre));lastSun=[...L.sunDir];
          gl.bindFramebuffer(gl.FRAMEBUFFER,shadowFbo);gl.viewport(0,0,shadowSize,shadowSize);gl.clear(gl.DEPTH_BUFFER_BIT);gl.useProgram(depth.p);gl.uniformMatrix4fv(depth.u.model,false,model.transform);gl.uniformMatrix4fv(depth.u.lightVP,false,lightVP);gl.enable(gl.POLYGON_OFFSET_FILL);gl.polygonOffset(1.1,2);gl.drawElements(gl.TRIANGLES,indices.length,gl.UNSIGNED_INT,0);gl.disable(gl.POLYGON_OFFSET_FILL);
        }
        resize(W,H);gl.bindFramebuffer(gl.FRAMEBUFFER,aaFbo||fbo);gl.viewport(0,0,W,H);gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
        gl.useProgram(material.p);const U=material.u;
        gl.uniformMatrix4fv(U.vp,false,vp);gl.uniformMatrix4fv(U.model,false,model.transform);gl.uniformMatrix4fv(U.lightVP,false,lightVP);gl.uniformMatrix3fv(U.rotation,false,model.rotation);
        gl.uniform3fv(U.summit,model.peak);gl.uniform3fv(U.camera,camera);gl.uniform3fv(U.sun,L.sunDir);gl.uniform3fv(U.sunCol,L.sun);gl.uniform3fv(U.fogCol,L.fog);gl.uniform1f(U.shadowPixel,1/shadowSize);
        gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,rockTex);gl.uniform1i(U.rockTexture,0);
        gl.activeTexture(gl.TEXTURE1);gl.bindTexture(gl.TEXTURE_2D,shadowTex);gl.uniform1i(U.shadowMap,1);gl.drawElements(gl.TRIANGLES,indices.length,gl.UNSIGNED_INT,0);
        if(aaFbo){
          gl.bindFramebuffer(gl.READ_FRAMEBUFFER,aaFbo);gl.bindFramebuffer(gl.DRAW_FRAMEBUFFER,fbo);
          for(let i=0;i<2;i++){gl.readBuffer(gl.COLOR_ATTACHMENT0+i);gl.drawBuffers(i===0?[gl.COLOR_ATTACHMENT0]:[gl.NONE,gl.COLOR_ATTACHMENT1]);gl.blitFramebuffer(0,0,w,h,0,0,w,h,gl.COLOR_BUFFER_BIT,gl.NEAREST);}
          gl.drawBuffers([gl.COLOR_ATTACHMENT0,gl.COLOR_ATTACHMENT1]);
        }
        gl.bindFramebuffer(gl.FRAMEBUFFER,null);gl.bindVertexArray(null);gl.disable(gl.DEPTH_TEST);gl.viewport(0,0,W,H);
      }
      return{render,colorTex,distanceTex,count:indices.length/3,samples,shadowSize,refinedCells};
    };
    return model;
  }
  window.HCKhumbu={load};
})();
