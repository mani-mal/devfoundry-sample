import { useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';

export default function ScrollToTop() {
  const location = useLocation();
  const prevLocation = useRef(location);

  useEffect(() => {
    if (prevLocation.current !== location) {
      window.scrollTo(0, 0);
      prevLocation.current = location;
    }
  }, [location]);

  return null;
}
