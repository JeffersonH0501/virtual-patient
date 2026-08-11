import {FC} from 'react';

type PauseIconProps = {
  className?: string;
  color?: string;
};

export const PauseIcon: FC<PauseIconProps> = ({className = '', color = 'currentColor'}) => {
  return (
    <svg
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      <path d="M6 4H10V20H6V4ZM14 4H18V20H14V4Z" fill={color} />
    </svg>
  );
};
