import { z } from 'zod';
export const createOrderSchema = z.object({
  userId: z.string().uuid(),
  modelId: z.string().min(1),
  mode: z.enum(['server', 'local']),
  payload: z.unknown(),
});
export const identitySchema = z.object({
  email: z.string().email(),
  password: z.string().min(12),
});