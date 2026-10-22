import { createFileRoute } from '@tanstack/react-router';
import { Saved } from '@/features/scholarpath/discovery';
import { pageHead } from '@/features/scholarpath/data';
export const Route=createFileRoute('/saved')({head:()=>pageHead('Saved Scholarships','Review and manage your shortlist of sample scholarship opportunities.'),component:Saved});
