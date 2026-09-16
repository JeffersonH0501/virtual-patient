export type User = {
  id: number;
  email: string;
  name: string;
  preferredLanguage: string;
  role: 'student' | 'teacher' | 'superuser';
};
