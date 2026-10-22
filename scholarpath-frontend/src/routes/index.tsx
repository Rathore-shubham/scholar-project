import { createFileRoute } from '@tanstack/react-router';
import { Dashboard } from '@/features/scholarpath/dashboard';
import { pageHead } from '@/features/scholarpath/data';
export const Route=createFileRoute('/')({head:()=>pageHead('Student Dashboard','Explore your sample scholarship matches, saved opportunities and upcoming application deadlines with ScholarPath AI.'),component:Dashboard});
