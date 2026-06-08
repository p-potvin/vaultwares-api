// /components/ui/ToastWithCorrelation.tsx
'use client';

import { toast } from 'sonner';

type ErrorWithCorrelation = {
  message: string;
  correlationId: string;
};

export const showErrorToast = ({ message, correlationId }: ErrorWithCorrelation) => {
  // Per guidelines: user-friendly toast, never silent, include CorrelationId
  toast.error(message, {
    description: `CorrelationId: ${correlationId}`,
    duration: 8000,
  });
};

export const showSuccessToast = (message: string) => {
  toast.success(message);
};
