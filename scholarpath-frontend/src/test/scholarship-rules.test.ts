import { describe, expect, it } from 'vitest';
import { scholarships, initialProfile, eligibility, criteria, profileSchema } from '@/features/scholarpath/data';
describe('ScholarPath sample rules',()=>{
 const sample=scholarships.find(s=>s.id==='national-merit');
 it('returns eligible only when all evaluated sample requirements pass',()=>{if(!sample)throw new Error('Missing sample');expect(eligibility(sample,initialProfile)).toBe('Eligible');});
 it('does not return eligible for a missing mandatory value',()=>{if(!sample)throw new Error('Missing sample');const {income,...partial}=initialProfile;expect(eligibility(sample,partial)).toBe("Can't Tell Yet");expect(criteria(sample,partial).find(r=>r.label==='Annual family income')?.pass).toBeNull();});
 it('explains a confirmed failed requirement',()=>{if(!sample)throw new Error('Missing sample');expect(eligibility(sample,{...initialProfile,percentage:45})).toBe('Not Eligible');expect(criteria(sample,{...initialProfile,percentage:45}).find(r=>r.label==='Academic percentage')?.pass).toBe(false);});
 it('rejects invalid profile inputs',()=>{expect(profileSchema.safeParse({...initialProfile,name:'',percentage:101,income:-5}).success).toBe(false);expect(profileSchema.safeParse({...initialProfile,dob:'2099-01-01'}).success).toBe(false);});
 it('marks every sample as unverified',()=>{expect(scholarships.every(s=>s.verified===null)).toBe(true);});
});
