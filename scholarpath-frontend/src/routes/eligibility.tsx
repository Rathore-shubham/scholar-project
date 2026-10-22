import { createFileRoute } from '@tanstack/react-router';
import { ProfileForm } from '@/features/scholarpath/profile';
import { pageHead } from '@/features/scholarpath/data';
export const Route=createFileRoute('/eligibility')({head:()=>pageHead('Eligibility Checker','Compare your student details against explicit mock scholarship rules, with criteria-by-criteria explanations.'),component:()=> <ProfileForm checker/>});
