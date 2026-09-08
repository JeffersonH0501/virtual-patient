import {FC, useState, useRef, useEffect} from 'react';
import {CaretDown} from '../../../icons';

type CustomSelectProps = {
  label: string;
  id: string;
  placeholder: string;
  value: string;
  onChange: (value: string) => void;
  options: string[];
  disabled?: boolean;
  margin?: boolean;
};

export const CustomSelect: FC<CustomSelectProps> = ({
  label,
  id,
  placeholder,
  value,
  onChange,
  options,
  disabled = false,
  margin = true,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  const handleOptionClick = (option: string) => {
    onChange(option);
    setIsOpen(false);
  };

  const toggleDropdown = () => {
    if (!disabled) {
      setIsOpen(!isOpen);
    }
  };

  return (
    <div className="flex flex-col">
      {label && (
        <label htmlFor={id} className="mb-3 block text-left text-sm text-black">
          {label}
        </label>
      )}
      <div
        className={`relative ${margin ? 'mt-2 mb-4' : ''} max-w-full text-sm text-black rounded-xl border border-gray-400 border-solid ${
          disabled ? 'bg-gray-100 cursor-not-allowed' : 'hover:border-gray-500 focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-200'
        }`}
      >
        <div
          ref={dropdownRef}
          className="relative"
        >
          <button
            type="button"
            onClick={toggleDropdown}
            disabled={disabled}
            className={`w-full text-left bg-transparent outline-none disabled:cursor-not-allowed cursor-pointer select-trigger-padding text-gray-900 ${
              disabled ? 'cursor-not-allowed' : 'cursor-pointer'
            }`}
            aria-haspopup="listbox"
            aria-expanded={isOpen}
            aria-label={label}
          >
            <span className={value ? 'text-gray-900' : 'text-gray-500'}>
              {value || placeholder}
            </span>
            <span className="absolute inset-y-0 right-0 flex items-center pr-3 pointer-events-none">
              <span
                className={`block h-5 w-5 text-gray-400 transition-transform duration-200 [&_svg]:h-full [&_svg]:w-full ${
                  isOpen ? 'rotate-180' : ''
                }`}
              >
                <CaretDown color="currentColor" />
              </span>
            </span>
          </button>

          {isOpen && (
            <div className="absolute z-50 w-full mt-1 bg-white border border-gray-300 rounded-lg shadow-lg max-h-60 overflow-auto">
              {options.map((option, index) => (
                <button
                  key={index}
                  type="button"
                  onClick={() => handleOptionClick(option)}
                  className={`w-full px-4 py-4 text-left text-sm text-gray-900 hover:bg-gray-100 focus:bg-gray-100 focus:outline-none ${
                    value === option ? 'bg-blue-50 text-blue-900' : ''
                  }`}
                  role="option"
                  aria-selected={value === option}
                >
                  <div className="flex items-center">
                    <span className={value === option ? 'font-medium' : ''}>
                      {option}
                    </span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
