import {FC} from 'react';
import {useNavigate} from 'react-router-dom';
import {useTranslation} from 'react-i18next';
import {ROUTES} from '../../utils/routes';

export const CustomCaseCard: FC = () => {
  const {t} = useTranslation();
  const navigate = useNavigate();

  const goToCreateCase = () => {
    navigate(ROUTES.createCase);
  };

  return (
    <div className="flex flex-col max-md:ml-0 max-md:w-full max-w-[480px] h-full">
      <div className="flex flex-col justify-between px-9 py-9 mx-auto w-full text-black rounded-2xl border-2 border-gray-200 border-solid bg-slate-50 max-md:px-5 max-md:mt-10 max-md:max-w-full h-full">
        <div>
          <img
            loading="lazy"
            src="https://cdn.builder.io/api/v1/image/assets/589f29fdf7d24550938c20c0ba89c2a1/846357857de706c727fbd526b3e97d1b47feac04eefe9e5aa2dc34c9b050380d?apiKey=589f29fdf7d24550938c20c0ba89c2a1&"
            className="object-contain ml-2.5 w-9 aspect-square"
            alt=""
          />
          <div className="mt-4 text-xl font-bold text-left">
            {t('clinicalCases.createCustomCase')}
          </div>
          <div className="mt-4 text-base font-small text-left">
            {t('clinicalCases.createCustomCaseDescription')}
          </div>
        </div>
        <button
          className="gap-2 self-stretch px-10 py-3 mt-8 text-lg text-blue-600 bg-white rounded-xl border border-blue-600 border-solid min-h-[45px] max-md:px-5 disabled:bg-gray-200 disabled:text-gray-400 disabled:border-gray-200"
          onClick={goToCreateCase}
        >
          {t('clinicalCases.createNew')}
        </button>
      </div>
    </div>
  );
};
