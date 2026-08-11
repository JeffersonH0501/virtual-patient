import {FC, useEffect} from 'react';
import {Footer} from '../common';
import {WelcomeSection} from '../Login/WelcomeSection';
import {SignUpForm} from './SignUpForm';
import {useTranslation} from 'react-i18next';
import {getAuthLanguage} from '../../utils/languageDetection';

export const SignUp: FC = () => {
  const {i18n} = useTranslation();

  // Set language to browser default for auth pages
  useEffect(() => {
    const authLanguage = getAuthLanguage();
    if (i18n.language !== authLanguage) {
      i18n.changeLanguage(authLanguage);
    }
  }, [i18n]);

  return (
    <div
      id="LoginPageContainer"
      className="flex flex-col pt-16 w-full bg-neutral-100 justify-between align-middle gap-[35px]"
    >
      <main
        id="WelcomeBoxWrapper"
        className="flex flex-col overflow-auto w-screen items-center justify-center"
      >
        <div className="flex flex-col rounded-none">
          <div className="pl-10 w-full bg-blue-600 rounded-l-3xl rounded-r-4xl shadow-xl max-md:pl-5 max-md:max-w-full">
            <div className="flex gap-5 max-md:flex-col">
              <WelcomeSection />
              <SignUpForm />
            </div>
          </div>
        </div>
      </main>
      <Footer />
    </div>
  );
};
