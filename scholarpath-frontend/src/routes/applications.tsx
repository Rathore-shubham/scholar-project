import { createFileRoute } from '@tanstack/react-router';
import { Applications } from '@/features/scholarpath/applications';
import { pageHead } from '@/features/scholarpath/data';
export const Route=createFileRoute('/applications')({head:()=>pageHead('My Applications','Track your self-reported scholarship application progress in ScholarPath AI.'),component:Applications});
