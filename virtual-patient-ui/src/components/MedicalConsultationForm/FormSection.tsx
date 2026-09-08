import {ReactNode} from 'react';

type FormSectionProps = {
  icon: ReactNode;
  title: string;
  children: ReactNode;
};

export const FormSection = ({icon, title, children}: FormSectionProps) => {
  return (
    <section>
      <header className="flex gap-2 items-center mb-7">
        <div className="h-5 w-5 text-blue-600 [&_svg]:h-full [&_svg]:w-full">{icon}</div>
        <h2 className="text-xl font-bold text-gray-800 max-sm:text-lg">{title}</h2>
      </header>
      {children}
    </section>
  );
};
