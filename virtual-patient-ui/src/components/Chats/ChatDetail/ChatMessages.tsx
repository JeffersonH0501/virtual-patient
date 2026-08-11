import {useEffect, useRef} from 'react';
import {ChatMessage} from '../../common';
import {Message} from '../../../types';

type ChatMessagesProps = {
  messages?: Message[];
  audioAutoPlayEnabled?: boolean;
};

export const ChatMessages = ({messages, audioAutoPlayEnabled = true}: ChatMessagesProps) => {
  const messagesContainerRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    if (messagesContainerRef.current) {
      messagesContainerRef.current.scrollTop = messagesContainerRef.current.scrollHeight;
    }
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  return (
    <div ref={messagesContainerRef} className="overflow-y-auto flex-1 p-6 border-b border-gray-200 min-h-0">
      {messages?.map((message, index) => (
        <ChatMessage key={index} message={message} audioAutoPlayEnabled={audioAutoPlayEnabled} />
      ))}
    </div>
  );
};
