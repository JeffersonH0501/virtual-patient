import {FC, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {useNavigate} from 'react-router-dom';
import {Modal} from '../common';
import {ClinicalSession} from '../ClinicalSession';
import type {ClinicalCaseSimplified} from '../../services/clinicalCases';
import {EditIcon} from '../../icons';
import {useUser} from '../../hooks';
import {ROUTES} from '../../utils/routes';

const DEFAULT_URL =
  'https://cdn.builder.io/api/v1/image/assets/589f29fdf7d24550938c20c0ba89c2a1/51382232e8f027614abcd5951bd4490d39158e54d4313d385421ed14dd4adfec?apiKey=589f29fdf7d24550938c20c0ba89c2a1&';

type CaseCardProps = {
  type: 'Default' | 'Custom';
  clinicalCase: ClinicalCaseSimplified;
  caseIndex: number;
};

export const CaseCard: FC<CaseCardProps> = ({type, clinicalCase, caseIndex}) => {
  const {t} = useTranslation();
  const {user} = useUser();
  const navigate = useNavigate();
  const [open, setOpen] = useState<boolean>(false);

  const close = () => {
    setOpen(false);
  };

  const handleEditClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigate(ROUTES.editCase.replace(':caseId', clinicalCase.id.toString()));
  };

  const showEditIcon = type === 'Custom' && (user?.role === 'teacher' || user?.role === 'superuser');

  return (
    <>
      <div className="flex flex-col max-md:ml-0 max-md:w-full max-w-[480px] h-full">
        <div className="flex flex-col justify-between px-9 py-8 mx-auto w-full bg-white rounded-2xl border-2 border-gray-200 border-solid max-md:px-5 max-md:mt-10 max-md:max-w-full h-full relative">
          <div>
            <div className="flex gap-5 max-md:flex-col w-full">
              <div className="flex flex-col max-md:ml-0 max-md:w-full w-full">
                <div className="flex flex-col grow items-start text-black max-md:mt-2">
                  <div className="flex flex-row w-[100%] items-start justify-between max-md:ml-0 max-md:w-full">
                    <img
                      loading="lazy"
                      src={DEFAULT_URL}
                      className="object-contain aspect-[1.23] w-[50px]"
                      alt=""
                    />
                    <div className="flex items-center gap-2">
                      <div className="px-4 p-1 text-sm font-bold text-center text-blue-600 whitespace-nowrap bg-blue-50 rounded-2xl max-md:mt-1.5">
                        {type === 'Default' ? t('clinicalCases.default') : t('clinicalCases.custom')}
                      </div>
                      {showEditIcon && (
                        <button
                          onClick={handleEditClick}
                          className="p-1.5 text-blue-600 hover:text-blue-800 hover:bg-blue-50 rounded-lg transition-colors"
                          title={t('clinicalCases.editCase')}
                        >
                          <EditIcon size={18} />
                        </button>
                      )}
                    </div>
                  </div>
                  <div className="mt-4 text-xl font-bold text-left">
                    {user?.role === 'student' ? t('clinicalCases.clinicalCaseWithIndex', {index: caseIndex}) : clinicalCase.title}
                  </div>
                  <div className="mt-4 text-base font-small text-left">
                    {clinicalCase.description}
                  </div>
                </div>
              </div>
            </div>
          </div>
          <button
            className="gap-2 self-stretch px-10 py-3 mt-8 text-lg font-bold text-white bg-blue-600 rounded-xl min-h-[45px] max-md:px-5"
            onClick={() => setOpen(true)}
          >
            {t('clinicalCases.startCase')}
          </button>
        </div>
      </div>
      <Modal size="medium" open={open} closeAction={close} closeOnOutsideClick>
        <ClinicalSession clinicalCase={clinicalCase} caseIndex={caseIndex} onCancel={close} />
      </Modal>
    </>
  );
};
