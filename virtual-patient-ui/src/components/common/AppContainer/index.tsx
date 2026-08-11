import {Outlet} from 'react-router-dom';
import {Header} from '../Header';
import {Footer} from '../Footer';
import {TokenExpiredScreen} from '../../TokenExpiredScreen';
import {useAuthError} from '../../../hooks/useAuthError';

export const AppContainer = () => {
  const { isTokenExpired } = useAuthError();

  if (isTokenExpired) {
    return <TokenExpiredScreen />;
  }

  return (
    <div className="flex flex-col min-h-screen pt-16 w-full bg-neutral-100">
      <Header />
      <main className="flex flex-col overflow-auto px-20 pt-10 w-screen h-[100%] items-center flex-1 mb-8">
        <div className="flex flex-col items-start w-full h-full">
          <Outlet />
        </div>
      </main>
      <Footer />
    </div>
  );
};
