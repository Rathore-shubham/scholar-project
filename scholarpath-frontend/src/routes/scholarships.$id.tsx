import { createFileRoute } from '@tanstack/react-router';
import { Details } from '@/features/scholarpath/details';
import { pageHead, scholarships } from '@/features/scholarpath/data';
export const Route=createFileRoute('/scholarships/$id')({head:({params})=>pageHead(scholarships.find(s=>s.id===params.id)?.name||'Scholarship unavailable','Review sample scholarship criteria, funding, documents and source verification status.'),component:ScholarshipDetails});
function ScholarshipDetails(){const {id}=Route.useParams();return <Details id={id}/>;}
