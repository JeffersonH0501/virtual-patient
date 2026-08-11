export type Message = {
  id: number;
  content: string;
  createdAt: string;
  senderType: 'user' | 'patient' | 'chatbot';
  messageMetadata?: {
    isNew?: boolean;
    sessionId?: string;
    threadId?: string;
  };
  interviewId: number;
  senderName?: string;
  senderAvatar?: string;
  audioUrl?: string;
};

export type SendMessageResponse = {
  messages: Message[];
  newMessageIds: number[];
};
