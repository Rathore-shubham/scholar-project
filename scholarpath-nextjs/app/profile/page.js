import { ProfileForm } from "@/features/scholarpath/profile";

export const metadata = {
  title: "My Profile",
  description: "Manage your education, preferences and student profile for scholarship matching.",
};

export default function ProfilePage() {
  return <ProfileForm />;
}
