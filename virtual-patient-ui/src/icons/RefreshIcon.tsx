import { FC } from 'react';

type RefreshIconProps = {
  color?: string;
  size?: number;
};

export const RefreshIcon: FC<RefreshIconProps> = ({ 
  color = '#000000', 
  size = 24 
}) => {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <path
        d="M4 12a8 8 0 0 1 8-8V2l4 4-4 4V6a6 6 0 1 0 6 6h2a8 8 0 0 1-16 0z"
        fill={color}
      />
    </svg>
  );
};
