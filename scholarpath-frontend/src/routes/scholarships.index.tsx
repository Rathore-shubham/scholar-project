import { createFileRoute } from '@tanstack/react-router';
import { Discovery } from '@/features/scholarpath/discovery';
import { pageHead } from '@/features/scholarpath/data';
export const Route=createFileRoute('/scholarships/')({validateSearch:(search:Record<string,unknown>)=>({q:typeof search.q==='string'?search.q:''}),head:()=>pageHead('Find Scholarships','Search and filter illustrative scholarship opportunities for Indian students.'),component:DiscoveryPage});
function DiscoveryPage(){const {q}=Route.useSearch();return <Discovery initialQuery={q}/>;}
