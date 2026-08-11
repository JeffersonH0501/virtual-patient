import React, {createContext, useContext, useEffect, useState, ReactNode} from 'react';
import {getEvaluationAspects, EvaluationAspectsResponse} from '../services/evaluations';
import {useUser} from '../hooks';

type EvaluationAspectsContextType = {
  aspects: EvaluationAspectsResponse['aspects'] | null;
  isLoading: boolean;
  error: string | null;
};

const EvaluationAspectsContext = createContext<EvaluationAspectsContextType | undefined>(undefined);

type EvaluationAspectsProviderProps = {
  children: ReactNode;
};

export const EvaluationAspectsProvider: React.FC<EvaluationAspectsProviderProps> = ({children}) => {
  const [aspects, setAspects] = useState<EvaluationAspectsResponse['aspects'] | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const {user, isLoading: userLoading} = useUser();

  useEffect(() => {
    // Only fetch aspects when user is authenticated and not loading
    if (!userLoading && user) {
      const fetchAspects = async () => {
        try {
          setIsLoading(true);
          setError(null);
          const response = await getEvaluationAspects();
          setAspects(response.aspects);
        } catch (err) {
          console.error('Failed to fetch evaluation aspects:', err);
          setError(err instanceof Error ? err.message : 'Failed to fetch evaluation aspects');
        } finally {
          setIsLoading(false);
        }
      };

      fetchAspects();
    }
  }, [user, userLoading]);

  const value: EvaluationAspectsContextType = {
    aspects,
    isLoading,
    error,
  };

  return (
    <EvaluationAspectsContext.Provider value={value}>{children}</EvaluationAspectsContext.Provider>
  );
};

export const useEvaluationAspects = (): EvaluationAspectsContextType => {
  const context = useContext(EvaluationAspectsContext);
  if (context === undefined) {
    throw new Error('useEvaluationAspects must be used within an EvaluationAspectsProvider');
  }
  return context;
};
