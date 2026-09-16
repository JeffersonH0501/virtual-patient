export type TeacherFeedbackBase = {
  feedback: string;
};

export type TeacherFeedback = {
  id: number;
  medicalInterviewId: number;
  teacherId: number;
  feedback: string;
  createdAt: string;
  teacherName?: string | null;
  reviewedByYou?: boolean | null;
};

export type CreateTeacherFeedbackRequest = TeacherFeedbackBase;

export type UpdateTeacherFeedbackRequest = {
  feedback?: string;
};
