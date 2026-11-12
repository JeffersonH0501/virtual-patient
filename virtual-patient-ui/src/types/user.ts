export type User = {
  id: number;
  email: string;
  name: string;
  createdAt?: string | null;
  preferredLanguage: string;
  role: 'student' | 'doctor' | 'admin';
  semesterRange?: 'first_four' | 'fifth_eighth' | 'ninth_plus' | null;
  university?: string | null;
};
