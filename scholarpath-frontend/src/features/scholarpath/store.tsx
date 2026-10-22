import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { z } from 'zod';
import { initialProfile, profileSchema, applicationStatuses, scholarships, type Profile, type ApplicationStatus } from './data';
type Store = {profile:Profile;saveProfile:(p:Profile)=>void;saved:string[];toggleSave:(id:string)=>void;applications:Record<string,{status:ApplicationStatus;updated:string}>;setStatus:(id:string,status:ApplicationStatus)=>void;notice:string;notify:(s:string)=>void};
const Context=createContext<Store|null>(null);
const storageSchema=z.object({profile:profileSchema,saved:z.array(z.string().max(100)).max(100),applications:z.record(z.string().max(100),z.object({status:z.enum(applicationStatuses),updated:z.string().max(30)}))});
export function ScholarProvider({children}:{children:ReactNode}){
 const [profile,setProfile]=useState(initialProfile);const [saved,setSaved]=useState(['national-merit','bright-futures','future-engineers']);const [applications,setApplications]=useState<Store['applications']>({'national-merit':{status:'Preparing Documents',updated:'2026-10-09'},'bright-futures':{status:'Interested',updated:'2026-10-08'},'future-engineers':{status:'Applied',updated:'2026-10-07'}});const [ready,setReady]=useState(false);const [notice,notify]=useState('');
 useEffect(()=>{try{const raw=localStorage.getItem('scholarpath.prototype.v1');if(raw){const result=storageSchema.safeParse(JSON.parse(raw));if(result.success){setProfile(result.data.profile);setSaved(result.data.saved.filter(id=>scholarships.some(s=>s.id===id)));setApplications(result.data.applications);}}}catch{notify('Your saved prototype data could not be loaded.');}setReady(true);},[]);
 useEffect(()=>{if(ready)try{localStorage.setItem('scholarpath.prototype.v1',JSON.stringify({profile,saved,applications}));}catch{notify('Changes could not be saved on this device.');}},[profile,saved,applications,ready]);
 useEffect(()=>{if(notice){const t=setTimeout(()=>notify(''),4500);return()=>clearTimeout(t);}return undefined;},[notice]);
 return <Context.Provider value={{profile,saveProfile:p=>{const parsed=profileSchema.safeParse(p);if(parsed.success){setProfile(parsed.data);notify('Profile saved on this device.');}},saved,toggleSave:id=>{if(!scholarships.some(s=>s.id===id))return;setSaved(prev=>prev.includes(id)?prev.filter(x=>x!==id):[...prev,id]);},applications,setStatus:(id,status)=>{if(!scholarships.some(s=>s.id===id)||!applicationStatuses.includes(status))return;setApplications(prev=>({...prev,[id]:{status,updated:new Date().toISOString().slice(0,10)}}));notify('Application status updated.');},notice,notify}}>{children}</Context.Provider>;
}
export function useScholar(){const c=useContext(Context);if(!c)throw new Error('ScholarProvider is required');return c;}
