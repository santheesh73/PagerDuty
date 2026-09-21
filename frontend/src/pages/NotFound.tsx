import React from 'react';
import { Link } from 'react-router-dom';
import { Button } from '../components/shared/Button';
import { Card } from '../components/shared/Card';
import { FileQuestion, ArrowLeft } from 'lucide-react';

export const NotFound: React.FC = () => {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <Card className="max-w-md w-full">
        <div className="flex flex-col items-center justify-center space-y-4 py-4">
          <div className="w-12 h-12 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-slate-400">
            <FileQuestion className="w-6 h-6" aria-hidden="true" />
          </div>
          <div className="space-y-1">
            <h2 className="text-xl font-bold text-white">404 — Page Not Found</h2>
            <p className="text-sm text-slate-400">
              The requested route does not exist or has been moved.
            </p>
          </div>
          <div className="pt-2">
            <Link to="/">
              <Button variant="primary" size="sm">
                <ArrowLeft className="w-3.5 h-3.5 mr-1.5" aria-hidden="true" />
                Return to Dashboard
              </Button>
            </Link>
          </div>
        </div>
      </Card>
    </div>
  );
};
