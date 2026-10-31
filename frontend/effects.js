export default function({data}) {
  const reduce = matchMedia('(prefers-reduced-motion: reduce)');
  if (!data?.enabled || reduce.matches) return;
  let scanFrame = 0, hovered = null;
  const phrases = [['Ask something','interesting.'],['Find something','surprising.'],['Explore your','data.'],['Discover the','story.']];
  let headline=null, timer=0, phrase=0, characters=0, deleting=false;
  function resetHeadline() {
    clearTimeout(timer);timer=0;
    if(headline) {
      headline.classList.remove('is-typing');
      headline.querySelector('[data-type-first]').textContent=phrases[0][0];
      headline.querySelector('[data-type-second]').textContent=phrases[0][1];
      headline.removeAttribute('data-typing-line');
    }
  }
  function typeStep() {
    timer=0;
    if(!headline?.isConnected || document.hidden || reduce.matches) return;
    const [first,second]=phrases[phrase];
    const full=first+'\n'+second;
    characters+=deleting?-1:1;
    const visible=full.slice(0,Math.max(0,characters));
    headline.querySelector('[data-type-first]').textContent=visible.split('\n')[0];
    headline.querySelector('[data-type-second]').textContent=visible.split('\n')[1] || '';
    headline.setAttribute('data-typing-line',characters>first.length?'second':'first');
    let delay=deleting?32:70;
    if(!deleting && characters>=full.length) {deleting=true;delay=2300;}
    else if(deleting && characters<=0) {deleting=false;phrase=(phrase+1)%phrases.length;delay=350;}
    timer=setTimeout(typeStep,delay);
  }
  function findHeadline() {
    const next=document.querySelector('.typing-headline');
    if(next===headline) return;
    resetHeadline();headline=next;phrase=0;characters=0;deleting=false;
    if(headline && !document.hidden && !reduce.matches) {
      headline.classList.add('is-typing');
      headline.querySelector('[data-type-first]').textContent='';
      headline.querySelector('[data-type-second]').textContent='';
      timer=setTimeout(typeStep,300);
    }
  }
  const nodes = new Set(), observed = new Set(), motionNodes = new Set();
  const selectors = '.st-key-composer,.st-key-scalar_result,.data-picture,[data-testid="stMetric"],[data-testid="stExpander"],[data-testid="stVegaLiteChart"]';
  const observer = new IntersectionObserver(entries => {
    for (const entry of entries) if(entry.isIntersecting) {
      entry.target.classList.add('fx-entered');
      observer.unobserve(entry.target);
    }
  }, {threshold:.08});
  const motionObserver = new IntersectionObserver(entries => {
    for(const entry of entries) entry.target.classList.toggle('fx-offscreen', !entry.isIntersecting);
  });
  function scan() {
    findHeadline();
    for(const node of observed) if(!node.isConnected) {observer.unobserve(node);observed.delete(node);}
    for(const node of motionNodes) if(!node.isConnected) {motionObserver.unobserve(node);motionNodes.delete(node);}
    for(const node of document.querySelectorAll(selectors)) if(!observed.has(node)) {
      observed.add(node); observer.observe(node);
    }
    for(const node of document.querySelectorAll('.query-hero,.auth-art,.data-picture,.askdb-logo')) if(!motionNodes.has(node)) {
      motionNodes.add(node);motionObserver.observe(node);
    }
  }
  scan();
  const mutation = new MutationObserver(records => {
    // Text updates from our typewriter are not structural page changes.
    if(!document.hidden && records.some(record => [...record.addedNodes].some(node => node.nodeType === 1)) && !scanFrame) {
      scanFrame=requestAnimationFrame(()=>{scanFrame=0;scan();});
    }
  });
  mutation.observe(document.querySelector('[data-testid="stMain"]') || document.body, {childList:true,subtree:true});
  function move(event) {
    if(event.pointerType !== 'mouse' || document.hidden || reduce.matches) return;
    const panel = event.target.closest(selectors);
    if(panel !== hovered) { hovered?.classList.remove('fx-spotlight'); hovered=panel;panel?.classList.add('fx-spotlight'); }
  }
  function click(event) {
    if(reduce.matches || document.hidden || nodes.size>=4 || !event.target.closest('button,[role="tab"],summary')) return;
    const burst=document.createElement('span');
    burst.className='fx-click-burst'; burst.setAttribute('aria-hidden','true');
    burst.style.left=`${event.clientX}px`; burst.style.top=`${event.clientY}px`;
    document.body.appendChild(burst); nodes.add(burst);
    burst.addEventListener('animationend',()=>{nodes.delete(burst);burst.remove();},{once:true});
  }
  function pause() {
    document.body.classList.toggle('fx-paused',document.hidden || reduce.matches);
    if(document.hidden || reduce.matches) {cancelAnimationFrame(scanFrame);scanFrame=0;hovered?.classList.remove('fx-spotlight');hovered=null;}
    if(document.hidden || reduce.matches) {clearTimeout(timer);timer=0; if(reduce.matches) {resetHeadline();phrase=0;characters=0;deleting=false;}}
    else {scan();if(headline?.isConnected && !timer) {headline.classList.add('is-typing');timer=setTimeout(typeStep,300);}}
  }
  pause();
  document.addEventListener('pointerover',move,{passive:true});
  document.addEventListener('click',click,{passive:true});
  document.addEventListener('visibilitychange',pause);
  reduce.addEventListener('change',pause);
  return () => {
    resetHeadline();
    cancelAnimationFrame(scanFrame);observer.disconnect();motionObserver.disconnect();mutation.disconnect();
    document.removeEventListener('pointerover',move); document.removeEventListener('click',click);
    document.removeEventListener('visibilitychange',pause);reduce.removeEventListener('change',pause);
    for(const node of observed) {node.classList.remove('fx-entered','fx-spotlight');node.style.removeProperty('--spot-x');node.style.removeProperty('--spot-y');}
    for(const node of motionNodes) node.classList.remove('fx-offscreen');
    for(const node of nodes) node.remove(); document.body.classList.remove('fx-paused');
  };
}
