import {readDesignNumber} from '../../utils/designTokens';

// Getters keep portal timing synchronized with the current CSS theme.
export const DURATION = {
  modals: {
    get short() {
 return readDesignNumber('--motion-modal-unmount-short');
},
    get medium() {
 return readDesignNumber('--motion-modal-unmount-medium');
},
    get long() {
 return readDesignNumber('--motion-modal-unmount-long');
},
  },
};
