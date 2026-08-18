import {KeyboardEvent, useState} from 'react';
import {useTranslation} from 'react-i18next';

type CallComposerProps = {
  disabled: boolean;
  onSend: (message: string) => void | Promise<void>;
};

export const CallComposer = ({disabled, onSend}: CallComposerProps) => {
  const {t} = useTranslation();
  const [message, setMessage] = useState('');

  const send = () => {
    const content = message.trim();
    if (!content || disabled) return;
    setMessage('');
    void onSend(content);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      send();
    }
  };

  return (
    <footer className="border-t border-slate-200 bg-white px-3 py-2.5 sm:px-4">
      <div className="mx-auto flex w-full max-w-3xl items-end gap-2">
        <label htmlFor="call-text-fallback" className="sr-only">
          {t('clinicalChat.typeYourResponse')}
        </label>
        <textarea
          id="call-text-fallback"
          rows={1}
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          placeholder={disabled ? t('clinicalChat.waitingForResponse') : t('clinicalChat.call.textFallback')}
          className="max-h-24 min-h-10 flex-1 resize-none rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm leading-5 text-slate-800 outline-none transition focus:border-blue-500 focus:ring-2 focus:ring-blue-100 disabled:bg-slate-100"
        />
        <button
          type="button"
          onClick={send}
          disabled={disabled || !message.trim()}
          className="h-10 rounded-lg bg-blue-600 px-4 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          {t('clinicalChat.sendMessage')}
        </button>
      </div>
    </footer>
  );
};
