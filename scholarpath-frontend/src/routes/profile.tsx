import { createFileRoute } from '@tanstack/react-router';
import { ProfileForm } from '@/features/scholarpath/profile';
import { pageHead } from '@/features/scholarpath/data';
export const Route=createFileRoute('/profile')({head:()=>pageHead('My Profile','Manage your education, preferences and student profile for scholarship matching.'),component:()=> <ProfileForm/>});
