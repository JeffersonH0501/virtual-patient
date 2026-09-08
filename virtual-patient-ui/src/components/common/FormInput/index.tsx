import React, {ChangeEvent, forwardRef, KeyboardEvent} from 'react';
import {CaretDown} from '../../../icons';

type FormInputProps = {
  label: string;
  type: string;
  id: string;
  placeholder: string;
  value: string;
  onChange: (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => void;
  onKeyDown?: (
    e: KeyboardEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>,
  ) => void;
  onBlur?: () => void;
  options?: string[]; // Only for select type
  margin?: boolean; // New prop for margin
  disabled?: boolean; // New prop for disabled state
  rows?: number; // For textarea type
  autoFocus?: boolean;
  resizable?: boolean; // For textarea resizing
  error?: string; // Error message to display
};

export const FormInput = forwardRef<
  HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement,
  FormInputProps
>(
  (
    {
      label,
      type = 'text',
      id,
      placeholder,
      value,
      onChange,
      onKeyDown,
      onBlur,
      options,
      margin = true,
      disabled = false,
      rows = 3,
      autoFocus = false,
      resizable = false,
      error,
    },
    ref,
  ) => {
    return (
      <div className="flex flex-col">
        {label && (
          <label htmlFor={id} className="mb-1 text-left text-black block">
            {label}
          </label>
        )}
        <div
          className={`relative p-3 ${margin ? 'mt-2 mb-4' : ''} max-w-full text-sm text-black rounded-xl border ${
            error
              ? 'border-red-500 border-solid'
              : 'border-gray-400 border-solid'
          } ${
            disabled
              ? 'bg-gray-100 cursor-not-allowed'
              : error
                ? 'hover:border-red-600 focus-within:border-red-500 focus-within:ring-2 focus-within:ring-red-200'
                : 'hover:border-gray-500 focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-200'
          }`}
        >
          {type === 'textarea' ? (
            <textarea
              ref={ref as React.Ref<HTMLTextAreaElement>}
              id={id}
              autoFocus={autoFocus}
              placeholder={placeholder}
              value={value}
              onChange={onChange}
              onKeyDown={onKeyDown}
              onBlur={onBlur}
              disabled={disabled}
              rows={rows}
              className={`w-full bg-transparent outline-none disabled:cursor-not-allowed ${
                resizable ? 'resize-y' : 'resize-none'
              }`}
              aria-label={label}
            />
          ) : type === 'select' ? (
            <>
              <select
                ref={ref as React.Ref<HTMLSelectElement>}
                id={id}
                autoFocus={autoFocus}
                value={value}
                onChange={onChange}
                onKeyDown={onKeyDown}
                onBlur={onBlur}
                disabled={disabled}
                className="w-full appearance-none cursor-pointer bg-transparent pr-8 text-gray-900 outline-none disabled:cursor-not-allowed"
                aria-label={label}
              >
                {options?.map((option, index) => (
                  <option
                    key={index}
                    value={option}
                    className="py-2 px-3 text-gray-900 bg-white hover:bg-gray-100"
                  >
                    {option}
                  </option>
                ))}
              </select>
              <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-gray-500 [&_svg]:h-5 [&_svg]:w-5">
                <CaretDown color="currentColor" />
              </span>
            </>
          ) : (
            <input
              ref={ref as React.Ref<HTMLInputElement>}
              type={type}
              id={id}
              autoFocus={autoFocus}
              placeholder={placeholder}
              value={value}
              onChange={onChange}
              onKeyDown={onKeyDown}
              onBlur={onBlur}
              disabled={disabled}
              className="w-full bg-transparent outline-none disabled:cursor-not-allowed"
              aria-label={label}
            />
          )}
        </div>
        {error && (
          <div className="mt-1 text-sm text-red-600">
            {error}
          </div>
        )}
      </div>
    );
  },
);

FormInput.displayName = 'FormInput';
