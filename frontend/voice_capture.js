/* Capture stays entirely in the browser until Stop. No speech/cloud SDK. */
const WORKLET = `class Capture extends AudioWorkletProcessor {
  constructor() {
    super(); this.buffer=new Float32Array(1024); this.offset=0; this.total=0; this.stopped=false;
    this.port.onmessage=()=>this.finish();
  }
  send() { if(this.offset) { const part=this.buffer.slice(0,this.offset); this.port.postMessage(part,[part.buffer]); this.offset=0; } }
  finish() { if(this.stopped)return; this.stopped=true; this.send(); this.port.postMessage({done:true}); }
  process(inputs) {
    if(this.stopped)return false;
    const channels=inputs[0]; if(!channels?.length)return true;
    for(let i=0;i<channels[0].length;i++) {
      let value=0; for(const channel of channels)value+=channel[i];
      this.buffer[this.offset++]=value/channels.length; this.total++;
      if(this.offset===this.buffer.length)this.send();
      if(this.total>=sampleRate*60){this.finish();return false;}
    }
    return true;
  }
} registerProcessor('askdb-capture',Capture);`;

export function encodeWav(chunks, rate) {
  const length=chunks.reduce((sum,chunk)=>sum+chunk.length,0);
  if(!length)throw new Error('empty');
  const audio=new Float32Array(length); let offset=0;
  for(const chunk of chunks){audio.set(chunk,offset);offset+=chunk.length;}
  const count=Math.min(16000*60,Math.floor(length*16000/rate));
  if(!count)throw new Error('empty');
  const buffer=new ArrayBuffer(44+count*2), view=new DataView(buffer);
  const text=(at,s)=>{for(let i=0;i<s.length;i++)view.setUint8(at+i,s.charCodeAt(i));};
  text(0,'RIFF');view.setUint32(4,36+count*2,true);text(8,'WAVE');text(12,'fmt ');
  view.setUint32(16,16,true);view.setUint16(20,1,true);view.setUint16(22,1,true);
  view.setUint32(24,16000,true);view.setUint32(28,32000,true);view.setUint16(32,2,true);view.setUint16(34,16,true);
  text(36,'data');view.setUint32(40,count*2,true);
  for(let i=0;i<count;i++) {
    const start=Math.floor(i*rate/16000), end=Math.min(length,Math.max(start+1,Math.floor((i+1)*rate/16000)));
    let sample=0;for(let j=start;j<end;j++)sample+=audio[j];sample=Math.max(-1,Math.min(1,sample/(end-start)));
    view.setInt16(44+i*2,sample<0?sample*32768:sample*32767,true);
  }
  return new Blob([buffer],{type:'audio/wav'});
}

export default function({parentElement,setTriggerValue}) {
  const button=parentElement.querySelector('.voice-capture-button');
  const label=button.querySelector('span'), status=parentElement.querySelector('.voice-capture-status');
  let phase='idle', disposed=false, context, stream, node, source, sink, timer, flushTimer, chunks=[], frames=0;
  let reader;
  function paint(next,message='') {
    phase=next;button.disabled=['requesting','stopping','sending'].includes(next);
    button.dataset.recording=String(next==='recording');button.setAttribute('aria-pressed',String(next==='recording'));
    label.textContent=({idle:'Use your voice',requesting:'Allow microphone…',recording:'Stop recording',stopping:'Preparing audio…',sending:'Transcribing…'})[next];
    status.textContent=message;
  }
  function release() {
    clearTimeout(timer);clearTimeout(flushTimer);
    stream?.getTracks().forEach(track=>track.stop());stream=null;
    if(node){node.port.onmessage=null;node.disconnect();node=null;}
    source?.disconnect();sink?.disconnect();source=sink=null;
    if(context){context.close().catch(()=>{});context=null;}
  }
  function fail(message) {release();chunks=[];if(!disposed)paint('idle',message);}
  function send() {
    if(disposed)return;
    const rate=context.sampleRate;
    release();paint('sending','Preparing your question for local transcription…');
    try {
      const wav=encodeWav(chunks,rate);chunks=[];
      reader=new FileReader();
      reader.onerror=()=>fail('Could not prepare the recording. Please try again.');
      reader.onload=()=>{
        if(disposed)return;
        setTriggerValue('audio',{wav:String(reader.result).split(',')[1]});
      };
      reader.readAsDataURL(wav);
    } catch {fail('No audio captured. Record a little longer and try again.');}
  }
  function stop() {
    if(phase!=='recording')return;
    paint('stopping','Recording stopped.');clearTimeout(timer);
    stream?.getTracks().forEach(track=>track.stop());
    node.port.postMessage('flush');
    flushTimer=setTimeout(()=>fail('Recording could not finish. Please try again.'),3000);
  }
  async function start() {
    if(phase!=='idle')return;
    if(!navigator.mediaDevices?.getUserMedia)return fail('Microphone access requires localhost or HTTPS in a supported browser.');
    paint('requesting','Allow microphone access if your browser asks.');chunks=[];frames=0;
    try {
      const Audio=window.AudioContext||window.webkitAudioContext;
      context=new Audio({sampleRate:16000});
      await context.resume();if(disposed)return;
      const acquired=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true},video:false});
      if(disposed){acquired.getTracks().forEach(track=>track.stop());return;}
      stream=acquired;
      if(!context.audioWorklet)throw new Error('worklet');
      const moduleUrl=URL.createObjectURL(new Blob([WORKLET],{type:'application/javascript'}));
      try{await context.audioWorklet.addModule(moduleUrl);}finally{URL.revokeObjectURL(moduleUrl);}
      if(disposed)return;
      node=new AudioWorkletNode(context,'askdb-capture');
      node.port.onmessage=({data})=>{
        if(disposed)return;
        if(data.done){if(phase==='recording'||phase==='stopping')send();return;}
        if(phase==='recording'||phase==='stopping') {
          const remaining=Math.max(0,context.sampleRate*60-frames);
          if(remaining){const part=data.length>remaining?data.slice(0,remaining):data;chunks.push(part);frames+=part.length;}
        }
      };
      source=context.createMediaStreamSource(stream);sink=context.createGain();sink.gain.value=0;
      source.connect(node);node.connect(sink);sink.connect(context.destination);
      for(const track of stream.getTracks())track.addEventListener('ended',stop,{once:true});
      paint('recording','Listening · stops automatically after 60 seconds.');
      timer=setTimeout(stop,60000);
    } catch(error) {
      if(disposed)return;
      fail(error.name==='NotAllowedError'?'Microphone permission was denied. Allow it in your browser and try again.':
           error.name==='NotFoundError'?'No microphone found. Connect a microphone and try again.':
           'Could not start the microphone. Check that another app is not using it, then try again.');
    }
  }
  function click(){if(phase==='recording')stop();else if(phase==='idle')start();}
  button.addEventListener('click',click);paint('idle');
  return ()=>{disposed=true;button.removeEventListener('click',click);reader?.abort();release();chunks=[];};
}
