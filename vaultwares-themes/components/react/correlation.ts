import { randomBytes } from 'crypto';
export const createCorrelationId = (): string => 'c' + randomBytes(3).toString('hex');