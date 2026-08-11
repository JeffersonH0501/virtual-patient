import {FC} from 'react';

type PlayIconProps = {
  className?: string;
  color?: string;
};

export const PlayIcon: FC<PlayIconProps> = ({className = '', color = 'currentColor'}) => {
  return (
    <svg
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      <path d="M8 5V19L19 12L8 5Z" fill={color} />
    </svg>
  );
};
