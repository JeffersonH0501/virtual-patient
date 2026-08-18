export type Message = {
  id: number;
  content: string;
  createdAt: string;
  senderType: 'user' | 'patient' | 'chatbot';
  messageMetadata?: {
    isNew?: boolean;
    sessionId?: string;
    threadId?: string;
    speechSynthesis?: {
      voice: string;
      stylePolicyVersion?: string;
      vocalStyle?: {
        profileKey: string;
        speakingRate: string;
        pauseFrequency: string;
        energy: string;
        intonationVariation: string;
        hesitationFrequency: string;
        deliveryTone: string;
      };
      provider?: string;
      model?: string;
      instructions?: string;
    };
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
