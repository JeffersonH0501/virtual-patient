export type User = {
  id: number;
  organizationId?: number | null;
  email: string;
  name: string;
  createdAt?: string | null;
  preferredLanguage: string;
  role: 'student' | 'teacher' | 'superuser';
};
