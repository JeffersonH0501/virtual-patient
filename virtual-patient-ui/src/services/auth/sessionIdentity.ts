let accountId: number | null = null;

export const getSessionAccountId = () => accountId;

export const setSessionAccountId = (id: number | null) => {
  accountId = id;
};
