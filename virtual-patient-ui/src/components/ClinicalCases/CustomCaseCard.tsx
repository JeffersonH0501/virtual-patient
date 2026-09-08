import {FC} from 'react';
import {useNavigate} from 'react-router-dom';
import {useTranslation} from 'react-i18next';
import {ROUTES} from '../../utils/routes';
import {CaretRight, PlusIcon} from '../../icons';

export const CustomCaseCard: FC = () => {
  const {t} = useTranslation();
  const navigate = useNavigate();

  return (
    <article className="group flex flex-col gap-4 rounded-2xl border border-dashed border-blue-300 bg-blue-50/50 p-4 text-left transition duration-200 hover:border-blue-400 hover:shadow-md sm:flex-row sm:items-center">
      <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-blue-600 text-white [&_svg]:h-6 [&_svg]:w-6">
        <PlusIcon color="currentColor" />
      </div>
      <div className="min-w-0 flex-1">
        <h3 className="text-base font-bold text-slate-950">
          {t('clinicalCases.createCustomCase')}
        </h3>
        <p className="mt-1 line-clamp-2 text-sm leading-5 text-slate-600">
          {t('clinicalCases.createCustomCaseDescription')}
        </p>
      </div>
      <button
        type="button"
        className="flex min-h-10 shrink-0 items-center gap-2 rounded-xl border border-blue-600 bg-white px-4 py-2 text-sm font-semibold text-blue-700 transition hover:bg-blue-600 hover:text-white focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-blue-200"
        onClick={() => navigate(ROUTES.createCase)}
      >
        <span>{t('clinicalCases.createNew')}</span>
        <span aria-hidden="true" className="block h-4 w-4 transition-transform group-hover:translate-x-1 [&_svg]:h-full [&_svg]:w-full">
          <CaretRight color="currentColor" />
        </span>
      </button>
    </article>
  );
};
