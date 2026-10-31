export default function({data}) {
  const nav=document.querySelector('.st-key-workspace_nav');
  if(!nav)return;
  const reduced=matchMedia('(prefers-reduced-motion: reduce)');
  let group,pill,animation,frame,disposed=false;
  function removePill(){animation?.cancel();animation=null;group?.classList.remove('nav-motion-ready');pill?.remove();pill=null;}
  function place(animate=true){
    if(disposed)return;
    const next=nav.querySelector('[data-testid="stButtonGroup"]');
    const selected=next?.querySelector('button[aria-pressed="true"],button[data-selected]');
    if(!next||!selected){removePill();return;}
    if(group!==next){removePill();group=next;}
    const parent=group.getBoundingClientRect(),rect=selected.getBoundingClientRect();
    if(!rect.width||!rect.height)return;
    const current={x:rect.left-parent.left+group.scrollLeft,y:rect.top-parent.top+group.scrollTop,w:rect.width,h:rect.height,page:data.page};
    let previous;
    try{previous=JSON.parse(nav.dataset.selectionBounds||'null');}catch{previous=null;}
    if(!pill){pill=document.createElement('div');pill.className='nav-selection-glide';pill.setAttribute('aria-hidden','true');group.appendChild(pill);}
    pill.style.width=current.w+'px';pill.style.height=current.h+'px';
    const target=`translate(${current.x}px,${current.y}px)`;
    pill.style.transform=target;group.classList.add('nav-motion-ready');
    if(animate&&data.enabled&&!reduced.matches&&previous&&previous.page!==current.page&&pill.animate){
      animation?.cancel();
      animation=pill.animate([
        {transform:`translate(${previous.x}px,${previous.y}px) scale(${previous.w/current.w},${previous.h/current.h})`},
        {transform:target}
      ],{duration:280,easing:'cubic-bezier(.22,1,.36,1)'});
    }
    nav.dataset.selectionBounds=JSON.stringify(current);
  }
  function schedule(){if(!frame)frame=requestAnimationFrame(()=>{frame=0;place();});}
  function settle(){animation?.cancel();place(false);}
  const changes=new MutationObserver(schedule);
  changes.observe(nav,{subtree:true,childList:true,attributes:true,attributeFilter:['aria-pressed','data-selected']});
  let size=nav.getBoundingClientRect();
  const resize=new ResizeObserver(()=>{
    const next=nav.getBoundingClientRect();
    if(next.width!==size.width||next.height!==size.height){size=next;place(false);}
  });resize.observe(nav);
  nav.addEventListener('scroll',settle,true);
  reduced.addEventListener('change',settle);
  place();
  return ()=>{disposed=true;cancelAnimationFrame(frame);changes.disconnect();resize.disconnect();nav.removeEventListener('scroll',settle,true);reduced.removeEventListener('change',settle);removePill();};
}
