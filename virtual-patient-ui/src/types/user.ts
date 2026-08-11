export type User = {
  id: number;
  username: string;
  email: string;
  fullName: string;
  preferredLanguage: string;
  role: 'student' | 'teacher' | 'superuser';
};
