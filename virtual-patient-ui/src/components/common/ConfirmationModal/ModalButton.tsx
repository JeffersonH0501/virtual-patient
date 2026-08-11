import {FC, ReactNode} from 'react';

type ModalButtonProps = {
  variant: 'primary' | 'secondary';
  onClick: () => void;
  children: ReactNode;
  disabled?: boolean;
};

export const ModalButton: FC<ModalButtonProps> = ({variant, onClick, children, disabled = false}) => {
  const baseStyles =
    'px-6 py-3 text-base rounded-lg h-[42px] max-sm:px-5 max-sm:py-3';
  const variantStyles = {
    primary: disabled 
      ? 'text-white bg-gray-400 border-[none] cursor-not-allowed' 
      : 'text-white bg-red-600 border-[none] cursor-pointer hover:bg-red-700',
    secondary: disabled
      ? 'text-gray-400 border border-gray-200 border-solid cursor-not-allowed'
      : 'text-gray-600 border border-gray-300 border-solid cursor-pointer hover:bg-gray-50',
  };

  return (
    <button 
      className={`${baseStyles} ${variantStyles[variant]}`} 
      onClick={onClick} 
      type="button"
      disabled={disabled}
    >
      {children}
    </button>
  );
};
