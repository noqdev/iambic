import React from 'react';
import { CookieConsent } from "@site/src/features/cookie-consent";

// Default implementation, that you can customize
export default function Root({children}) {
  return <>
  {children}
  <CookieConsent />
  </>;
}