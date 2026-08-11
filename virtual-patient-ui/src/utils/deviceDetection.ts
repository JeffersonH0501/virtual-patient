/**
 * Detects if the current device is a mobile device
 * @returns true if the device is mobile, false otherwise
 */
export const isMobileDevice = (): boolean => {
  if (typeof window === 'undefined') {
    return false;
  }

  // Check user agent for mobile devices
  const userAgent = navigator.userAgent || navigator.vendor || (window as any).opera;
  
  // Common mobile device patterns
  const mobileRegex = /android|webos|iphone|ipad|ipod|blackberry|iemobile|opera mini/i;
  
  // Check user agent
  if (mobileRegex.test(userAgent)) {
    return true;
  }
  
  // Check screen width (mobile devices typically have smaller screens)
  // This is a fallback for devices that might not be detected by user agent
  if (window.innerWidth <= 768) {
    return true;
  }
  
  // Check for touch support (most mobile devices have touch)
  // But be careful - some laptops also have touch screens
  const hasTouchScreen = 'ontouchstart' in window || navigator.maxTouchPoints > 0;
  if (hasTouchScreen && window.innerWidth <= 1024) {
    return true;
  }
  
  return false;
};

