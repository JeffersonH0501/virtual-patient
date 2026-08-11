export type SessionNoteBase = {
  notesContent: string;
};

export type SessionNote = {
  id: number;
  interviewId: number;
  notesContent: string;
  createdAt: string;
  updatedAt: string;
};

export type CreateSessionNoteRequest = SessionNoteBase;

export type UpdateSessionNoteResponse = SessionNote;

