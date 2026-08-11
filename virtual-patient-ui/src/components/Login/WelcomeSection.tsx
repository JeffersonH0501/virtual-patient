import loginImage from '../../assets/login.svg';
import {FC} from 'react';
import logoDisc from '/src/assets/logo_disc.png';
import {useTranslation} from 'react-i18next';

export const WelcomeSection: FC = () => {
  const {t} = useTranslation();

  return (
    <div key="WelcomeSectionContainer" className="flex flex-col w-[41%] max-md:ml-0 max-md:w-full">
      <div className="flex flex-col mt-16 text-black max-md:mt-10">
        <h2 className="text-4xl font-bold text-white max-md:mr-2.5 text-left">
          {t('auth.appTitle')}
        </h2>
        <p className="mt-12 text-xl font-medium text-white max-md:mt-10 text-left">
          {t('auth.appDescription')}
        </p>
        <img
          src={loginImage}
          alt="Anamnesis Clinical Virtual Patient"
          className="mt-8 w-full h-auto rounded-lg shadow-md"
        />
        <div className="flex items-center gap-2 mt-8">
          <img src={logoDisc} alt="Logo" className="h-20 w-auto" />
        </div>
      </div>
    </div>
  );
};
