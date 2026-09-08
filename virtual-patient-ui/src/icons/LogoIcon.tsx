import {IconProps} from './types';

export const LogoIcon = ({color = 'currentColor'}: IconProps) => (
  <svg viewBox="0 0 174 32" fill="none" xmlns="http://www.w3.org/2000/svg">
    <text
      fill={color}
      xmlSpace="preserve"
      className="logo-text"
      fontFamily="Arial, sans-serif"
      fontSize="21"
      fontWeight="600"
      letterSpacing="0em"
    >
      <tspan x="50.7061" y="23.35">
        DoctorBot
      </tspan>
    </text>
    <text
      fill={color}
      xmlSpace="preserve"
      className="logo-text"
      fontFamily="Arial, sans-serif"
      fontSize="21"
      fontWeight="600"
      letterSpacing="0em"
    >
      <tspan x="20" y="23.35">
        VP
      </tspan>
    </text>
  </svg>
);
