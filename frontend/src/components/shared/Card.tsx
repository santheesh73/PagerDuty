import React from 'react';

interface CardProps {
  title?: string;
  children: React.ReactNode;
  className?: string;
}

export const Card: React.FC<CardProps> = ({ title, children, className = '' }) => {
  return (
    <div className={`bg-slate-900 border border-slate-800 rounded-xl p-6 shadow-sm ${className}`}>
      {title && <h3 className="text-lg font-semibold text-slate-100 mb-4">{title}</h3>}
      {children}
    </div>
  );
};
