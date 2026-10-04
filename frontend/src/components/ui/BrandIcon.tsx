import React from 'react';
import { useUI } from '../../context/UIContext';

type BrandIconProps = Omit<React.ImgHTMLAttributes<HTMLImageElement>, 'src' | 'srcSet'>;

/** Keeps the app's C + check legible across the twelve supported themes. */
export const BrandIcon: React.FC<BrandIconProps> = ({ alt = '', ...props }) => {
  const { theme } = useUI();
  const lightSurface = theme === 'light' || theme === 'sepia';
  return (
    <img
      {...props}
      src={lightSurface ? '/concurse-icon-light-64.png' : '/concurse-icon-64.png'}
      alt={alt}
    />
  );
};
