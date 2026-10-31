export default function({parentElement,data,setTriggerValue}) {
  const grid=parentElement.querySelector('.starter-cards');
  const cleanups=[];
  for(const [index,item] of (data?.items||[]).entries()) {
    const button=document.createElement('button');
    button.type='button';button.className='starter-card';
    const meta=document.createElement('span');meta.className='starter-card-meta';meta.setAttribute('aria-hidden','true');
    const number=document.createElement('span');number.textContent=String(index+1).padStart(2,'0');
    const arrow=document.createElement('span');arrow.textContent='↗';
    meta.append(number,arrow);
    const copy=document.createElement('span');copy.className='starter-card-copy';
    const title=document.createElement('span');title.className='starter-card-title';title.textContent=item.title;
    const description=document.createElement('span');description.className='starter-card-description';description.textContent=item.question;
    copy.append(title,description);button.append(meta,copy);grid.appendChild(button);
    const click=()=>setTriggerValue('selected',{index,source:data.source});
    button.addEventListener('click',click);
    cleanups.push(()=>{button.removeEventListener('click',click);button.remove();});
  }
  return ()=>cleanups.forEach(cleanup=>cleanup());
}
